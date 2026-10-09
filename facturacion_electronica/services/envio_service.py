"""Transmisión del DE firmado a SIFEN y consulta de su estado.

Síncrona (`siRecepDE`) por defecto; por lote si así se configuró (ver
`envio_lote.py`).
"""
from datetime import datetime

from app import db
from facturacion_electronica import (
    AMBIENTE_PRODUCCION,
    ESTADO_ENVIADO,
    ESTADO_ERROR,
    MODO_ENVIO_LOTE,
    ESTADOS_NO_REGENERABLES,
    SIN_REINTENTO,
)
from facturacion_electronica.services.config_service import obtener_configuracion
from facturacion_electronica.services.crypto import descifrar
from facturacion_electronica.services.documento_consulta import fecha_emision
from facturacion_electronica.services.envio_lote import (
    consultar_lote_del_documento,
    enviar_en_lote,
    es_de_lote_propio,
    modo_envio_efectivo,
)
from facturacion_electronica.services.guarda import error_venta_no_facturable
from facturacion_electronica.services.respuesta_sifen import (
    _interpretar_respuesta,
    _serializar_respuesta,
)
from facturacion_electronica.services.retransmision import (
    aplicar_consulta,
    evaluar_plazo,
    verificar_antes_de_reenviar,
)
from facturacion_electronica.services.sifen_client import (
    consultar_de,
    consultar_lote,
    enviar_de,
    enviar_lote,
)


# Plazo de transmisión en término (MT v150 A004b). Pasado, SIFEN aprueba con
# observación (1005): es el límite para **facturar** una venta vieja, no para
# reenviar una ya firmada, que llega hasta las 720h (ver retransmision.py).
HORAS_LIMITE_ENVIO = 72


def _ambiente_setapi(config):
    return 'prod' if config.ambiente == AMBIENTE_PRODUCCION else 'test'


def enviar_documento(documento, forzar_fecha=False):
    """Envía el DE firmado a SIFEN y guarda la respuesta. Devuelve (doc, error).

    NO está probado end-to-end: requiere un certificado real habilitado por la
    DNIT (TLS mutuo). El circuito interno (generar/firmar/QR) sí está probado.
    """
    if documento is None or not documento.xml_firmado:
        return documento, 'Primero generá y firmá el documento antes de enviarlo.'
    if not documento.xml_qr:
        # gCamFuFD/dCarQR es obligatorio en el rDE; sin QR, SIFEN rechaza el envío.
        return documento, 'Primero generá el QR del documento antes de enviarlo.'
    if documento.estado in ESTADOS_NO_REGENERABLES:
        return documento, f'El documento ya está {documento.estado}.'
    error_venta = error_venta_no_facturable(getattr(documento, 'venta', None))
    if error_venta:
        documento.estado = ESTADO_ERROR
        documento.respuesta_mensaje = error_venta
        db.session.commit()
        return documento, error_venta

    # Pasadas 72h se envía igual (SIFEN aprueba con observación 1005); el
    # límite duro es 720h. Ver retransmision.py.
    error, aviso_plazo = (None, None) if forzar_fecha else evaluar_plazo(fecha_emision(documento))
    if error:
        # Persistido como error para que se vea en la UI, y definitivo: el
        # estado 'error' solo no frena al job, que lo tomaría cada 10 minutos
        # para siempre por algo que el tiempo no arregla.
        documento.estado = ESTADO_ERROR
        documento.respuesta_mensaje = error
        documento.reintentar_despues = SIN_REINTENTO
        db.session.commit()
        return documento, error

    config = obtener_configuracion()
    if not config.cert_path:
        return documento, 'Falta cargar el certificado digital (.p12) en la configuración.'

    if documento.estado == ESTADO_ERROR and documento.cdc:
        # El intento anterior falló al transmitir: pudo haber llegado igual.
        seguir, error = verificar_antes_de_reenviar(documento, lambda cdc: consultar_de(
            cdc, config.cert_path, descifrar(config.cert_password or ''),
            _ambiente_setapi(config), request_id=documento.id,
        ))
        if not seguir:
            return documento, error

    if modo_envio_efectivo(config) == MODO_ENVIO_LOTE:
        return enviar_en_lote(documento, lambda xmls: enviar_lote(
            xmls, config.cert_path, descifrar(config.cert_password or ''),
            _ambiente_setapi(config), request_id=documento.id,
        ), aviso_plazo=aviso_plazo)

    xml = documento.xml_qr
    respuesta, error = enviar_de(
        xml, config.cert_path, descifrar(config.cert_password or ''),
        _ambiente_setapi(config), request_id=documento.id,
    )
    if error:
        documento.estado = ESTADO_ERROR
        documento.respuesta_mensaje = error
        db.session.commit()
        return documento, error

    estado, codigo, mensaje, protocolo = _interpretar_respuesta(respuesta)
    documento.estado = estado
    documento.respuesta_codigo = str(codigo) if codigo is not None else None
    documento.respuesta_mensaje = ' '.join(
        p for p in (str(mensaje) if mensaje is not None else '', aviso_plazo or '') if p
    ) or None
    documento.respuesta_raw = _serializar_respuesta(respuesta)
    documento.protocolo_autorizacion = str(protocolo) if protocolo is not None else None
    documento.fecha_envio = datetime.utcnow()
    # Si antes viajó en un lote, ese número ya no es el de este envío: sin
    # borrarlo, la consulta preguntaría por el lote viejo.
    documento.api_lote_id = None
    db.session.commit()
    return documento, None


def consultar_documento(documento):
    """Consulta el estado actual del DE en SIFEN por CDC. Devuelve (respuesta, error)."""
    if documento is None or not documento.cdc:
        return None, 'No hay CDC para consultar.'
    config = obtener_configuracion()
    if not config.cert_path:
        return None, 'Falta cargar el certificado digital (.p12) en la configuración.'
    password = descifrar(config.cert_password or '')
    ambiente = _ambiente_setapi(config)

    def consultar_cdc(cdc):
        return consultar_de(cdc, config.cert_path, password, ambiente, request_id=documento.id)

    if documento.estado == ESTADO_ENVIADO and es_de_lote_propio(documento):
        # Por CDC daría 0420 mientras el lote se procesa, y eso lo marcaría
        # rechazado. Se respeta cómo salió, no el modo configurado hoy.
        return consultar_lote_del_documento(documento, lambda numero: consultar_lote(
            numero, config.cert_path, password, ambiente, request_id=documento.id,
        ), consultar_cdc)

    respuesta, error = consultar_cdc(documento.cdc)
    if error:
        return respuesta, error
    # siConsDE responde `0422 CDC encontrado` con el protocolo dentro de
    # `xContenDE` (texto, no nodo), sin `dEstRes`: leído como un envío, nunca
    # pasaba a aprobado. Sólo avanza con evidencia; nunca retrocede.
    aplicar_consulta(documento, respuesta)
    return respuesta, None
