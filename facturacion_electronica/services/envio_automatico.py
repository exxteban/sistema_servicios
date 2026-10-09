"""Avanza automáticamente los documentos electrónicos pendientes.

El POS arma, firma y calcula el QR del DE en el momento de la venta, pero no
lo envía a SIFEN (para no bloquear el checkout con una llamada de red). Sin
este job, el envío quedaría 100% manual (botón por venta), lo cual es
inviable con la ventana de 72h que exige SIFEN. Se llama periódicamente desde
un scheduler en background (ver app/bootstrap/runtime.py), igual que el de
timeouts de WhatsApp.

Nunca lanza: cada documento se procesa de forma aislada y el motivo del fallo
queda en el propio documento (`respuesta_mensaje` + `reintentar_despues`) para
reintentarse en la pasada siguiente al backoff.

El estado fiscal y el fallo de transporte son cosas distintas y se guardan por
separado: un DE que no se pudo firmar porque el servicio Node está caído sigue
siendo un DE 'generado', no uno en 'error'. Sólo se mueve el estado cuando lo
que falla es el documento en sí (una venta anulada, las 720h de SIFEN vencidas).
"""
from datetime import datetime, timedelta

from flask import current_app

from app import db
from facturacion_electronica import (
    ESTADO_API_CANCELACION_PENDIENTE,
    ESTADO_APROBADO,
    ESTADO_ENVIADO,
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    ESTADO_GENERADO,
    ESTADO_RECHAZADO,
    SIN_REINTENTO,
    TIPO_FACTURA,
)
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.config_service import obtener_configuracion
from facturacion_electronica.services.guarda import (
    documento_en_proveedor,
    error_venta_no_facturable,
    fuera_de_plazo_de_transmision,
)
from facturacion_electronica.services.proveedores.fachada import avanzar_documento
from facturacion_electronica.services.proveedores.pertenencia import filtro_documentos_del_proveedor
from facturacion_electronica.services.validacion import validar_configuracion

# Estados en los que un documento todavía necesita que este job actúe.
ESTADOS_PENDIENTES = (ESTADO_GENERADO, ESTADO_FIRMADO, ESTADO_ENVIADO, ESTADO_ERROR)

# Los mismos sin 'error': ese entra por su propia condición, con el backoff.
ESTADOS_PENDIENTES_SIN_ERROR = tuple(e for e in ESTADOS_PENDIENTES if e != ESTADO_ERROR)

# Una cancelación pedida a la API queda en CANCELLATION_PENDING hasta que SIFEN
# la confirma, y ese estado sigue siendo 'aprobado' de nuestro lado (el DE vale
# hasta que la baja esté firme). Sin esa excepción en el filtro de abajo nadie
# vuelve a consultarlo: la factura quedaría figurando como aprobada para
# siempre después de anularla. El nombre del estado vive en el paquete.

# Evita reintentar un documento en 'error' en cada pasada del scheduler: si la
# causa es permanente (venta vieja, timbrado agotado) el chequeo es barato y
# no llega a golpear la red, pero si es transitoria (servicio Node caído) le
# da tiempo a recuperarse antes de reintentar.
REINTENTO_BACKOFF = timedelta(minutes=10)


def _rechazo_por_schema_de_la_api():
    """Rechazos que se reenvían solos: el `0160` del XML de la API.

    Hasta su 1.7.1 (2026-09-25) todo DE de la API salía sin
    `xsi:schemaLocation` y SIFEN lo rechazaba con `0160` "No se informó el
    schema". El error era del XML de ellos, no de nuestros datos, así que se
    corrige y reenvía con el mismo número sin que nadie toque nada. Cualquier
    otro rechazo espera a que una persona corrija lo que dice SIFEN.

    No hay rueda: si el reenvío falla o vence el plazo, el mensaje del
    documento cambia y deja de coincidir con este filtro.
    """
    mensaje = DocumentoElectronico.respuesta_mensaje
    return db.and_(
        DocumentoElectronico.estado == ESTADO_RECHAZADO,
        DocumentoElectronico.api_documento_id.isnot(None),
        # `correct/` es sólo para facturas.
        db.or_(
            DocumentoElectronico.tipo_documento.is_(None),
            DocumentoElectronico.tipo_documento == TIPO_FACTURA,
        ),
        mensaje.like('%0160%'),
        mensaje.ilike('%schema%'),
    )


def _marcar_fallo(documento, mensaje):
    """Deja el motivo a la vista y posterga el próximo intento.

    No toca `estado`: lo que falló es el intento, no lo que SIFEN sabe del
    documento. Mover acá el estado a 'error' debilitaría las guardias de
    anulación, que miran el estado para saber si el DE ya salió.
    """
    documento.respuesta_mensaje = str(mensaje)[:2000]
    # Un fallo ya declarado definitivo no vuelve al backoff común: pisarlo con
    # 10 minutos lo devolvería a la rueda de reintentos eternos.
    if documento.reintentar_despues != SIN_REINTENTO:
        documento.reintentar_despues = datetime.utcnow() + REINTENTO_BACKOFF
    db.session.commit()


def _marcar_exito(documento):
    """El documento avanzó: si arrastraba un backoff, se limpia."""
    if documento.reintentar_despues is not None:
        documento.reintentar_despues = None
        db.session.commit()


def _avanzar(documento):
    """Hace progresar el documento un paso más. El circuito lo decide el proveedor."""
    error_venta = error_venta_no_facturable(getattr(documento, 'venta', None))
    if error_venta and not documento_en_proveedor(documento):
        documento.estado = ESTADO_ERROR
        documento.respuesta_mensaje = error_venta
        db.session.commit()
        return error_venta
    if documento.estado == ESTADO_RECHAZADO and fuera_de_plazo_de_transmision(documento.venta):
        return ('SIFEN rechazó la factura y ya pasaron las 720h de la venta: no se puede '
                'reenviar. Corresponde inutilizar el número.')
    return avanzar_documento(documento)


def procesar_pendientes(limite=25):
    """Recorre los documentos pendientes y avanza cada uno. Devuelve un resumen para loguear."""
    resumen = {'procesados': 0, 'ok': 0, 'error': 0}

    config = obtener_configuracion()
    if validar_configuracion(config):
        # Configuración incompleta (falta certificado, CSC, timbrado, etc.):
        # todavía no hay nada que este job pueda enviar.
        return resumen

    ahora = datetime.utcnow()
    # El backoff se aplica **en el query**, no salteando filas ya traídas. Un
    # documento en error permanente (una venta a crédito, un timbrado agotado)
    # ocupaba igual su lugar entre los `limite` que devuelve el LIMIT, y con
    # `limite` documentos así las facturas nuevas —que tienen id más alto— no
    # entraban nunca a la ventana: el job quedaba trancado sin avisar nada.
    reintentable_desde = ahora - REINTENTO_BACKOFF
    pendientes = (
        DocumentoElectronico.query
        # Con el proveedor cambiado (pruebas), los documentos del otro quedan
        # quietos: el motor propio marcaba rechazada una factura de la API con
        # su lote en proceso, y la API re-emitía lo que el propio ya mandó.
        .filter(filtro_documentos_del_proveedor(config.proveedor))
        # El backoff de transporte tapa a todos los estados, no sólo a 'error':
        # un fallo al firmar deja el DE en 'generado' y ese estado no tiene
        # ninguna otra cosa que frene el reintento.
        .filter(db.or_(
            DocumentoElectronico.reintentar_despues.is_(None),
            DocumentoElectronico.reintentar_despues <= ahora,
        ))
        .filter(db.or_(
            DocumentoElectronico.estado.in_(ESTADOS_PENDIENTES_SIN_ERROR),
            db.and_(
                DocumentoElectronico.estado == ESTADO_ERROR,
                db.or_(
                    DocumentoElectronico.updated_at.is_(None),
                    DocumentoElectronico.updated_at <= reintentable_desde,
                ),
            ),
            db.and_(
                DocumentoElectronico.estado == ESTADO_APROBADO,
                DocumentoElectronico.respuesta_codigo == ESTADO_API_CANCELACION_PENDIENTE,
            ),
            _rechazo_por_schema_de_la_api(),
        ))
        .order_by(DocumentoElectronico.id.asc())
        .limit(limite)
        .all()
    )

    # Se recorre por id: un rollback en una fila no puede dejar a las
    # siguientes detached e impedir que se procesen.
    for doc_id in [documento.id for documento in pendientes]:
        documento = db.session.get(DocumentoElectronico, doc_id)
        if documento is None:
            continue
        resumen['procesados'] += 1
        try:
            error = _avanzar(documento)
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception(
                'Error al avanzar documento electrónico id=%s', doc_id,
            )
            documento = db.session.get(DocumentoElectronico, doc_id)
            if documento is not None:
                _marcar_fallo(documento, f'Error inesperado al procesar el documento: {exc}')
            resumen['error'] += 1
            continue
        if error:
            _marcar_fallo(documento, error)
            resumen['error'] += 1
        else:
            _marcar_exito(documento)
            resumen['ok'] += 1

    return resumen


__all__ = ['procesar_pendientes']
