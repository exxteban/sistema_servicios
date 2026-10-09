"""Eventos del emisor ante SIFEN: cancelación de un DE aprobado e
inutilización de un número que nunca llegó a transmitirse."""
from datetime import datetime, timedelta

from app import db
from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_INUTILIZADO,
    TIPO_FACTURA,
)
from facturacion_electronica.services.config_service import obtener_configuracion
from facturacion_electronica.services.crypto import descifrar
from facturacion_electronica.services.documento_consulta import fecha_emision
from facturacion_electronica.services.envio_service import _ambiente_setapi
from facturacion_electronica.services.guarda import (
    error_motivo_inutilizacion,
    error_numero_no_inutilizable,
    error_timbrado_inutilizacion,
)
from facturacion_electronica.services.respuesta_sifen import (
    _detalle_sifen,
    _interpretar_respuesta,
    _serializar_respuesta,
)
from facturacion_electronica.services.sifen_client import cancelar_de, inutilizar_de
from facturacion_electronica.services.tips_payload import construir_params_emisor


# SIFEN admite el evento de cancelación hasta ~48h después de la emisión.
# Pasado ese plazo la única salida es la nota de crédito (`generar_nota_credito`).
HORAS_LIMITE_CANCELACION = 48


def _fecha_firma_evento():
    """`dFecFirma` del evento, en hora de Paraguay y sin offset.

    La escribe el Node con la hora local **de su proceso**; en un servidor en
    UTC eso son tres horas en el futuro y SIFEN rechaza el evento con un error
    genérico. Se manda resuelta desde acá, igual que `dFeEmiDE` de la factura.
    """
    from app.utils.helpers import now_local

    return now_local().strftime('%Y-%m-%dT%H:%M:%S')


def cancelar_documento(documento, motivo):
    """Cancela en SIFEN un DE aprobado (evento). Devuelve (documento, error).

    No revierte la venta ni habilita re-facturación por sí sola: sólo anula el
    DE en SIFEN. Tras cancelar, generar_documento crea un DE nuevo si se quiere
    volver a facturar la misma venta.
    """
    if documento is None:
        return documento, 'No hay documento para cancelar.'
    if documento.estado == ESTADO_CANCELADO:
        return documento, 'El documento ya está cancelado.'
    if documento.estado != ESTADO_APROBADO:
        return documento, 'Sólo se puede cancelar en SIFEN un documento aprobado.'

    motivo = (motivo or '').strip()
    if not 5 <= len(motivo) <= 500:
        return documento, 'El motivo de cancelación debe tener entre 5 y 500 caracteres.'

    referencia = fecha_emision(documento)
    if referencia and datetime.utcnow() - referencia > timedelta(hours=HORAS_LIMITE_CANCELACION):
        return documento, (
            f'Pasaron más de {HORAS_LIMITE_CANCELACION}h desde la emisión; SIFEN ya no '
            'permite cancelar. Corresponde emitir una nota de crédito.'
        )

    config = obtener_configuracion()
    if not config.cert_path:
        return documento, 'Falta cargar el certificado digital (.p12) en la configuración.'

    params = construir_params_emisor(config)
    respuesta, xml_evento, error = cancelar_de(
        params, documento.cdc, motivo, config.cert_path,
        descifrar(config.cert_password or ''), _ambiente_setapi(config),
        request_id=documento.id, fecha_firma=_fecha_firma_evento(),
    )
    if error:
        return documento, error

    estado, codigo, mensaje, _protocolo = _interpretar_respuesta(respuesta)
    if estado != ESTADO_APROBADO:
        documento.respuesta_codigo = str(codigo) if codigo is not None else documento.respuesta_codigo
        documento.respuesta_mensaje = str(mensaje) if mensaje is not None else documento.respuesta_mensaje
        documento.respuesta_raw = _serializar_respuesta(respuesta)
        # El evento rechazado se guarda igual. Guardarlo sólo al aprobar dejaba
        # el rechazo sin nada que mirar: el mensaje de SIFEN es genérico y el
        # XML que se firmó —lo único que dice qué se mandó— se perdía.
        documento.xml_cancelacion = xml_evento
        db.session.commit()
        return documento, f'SIFEN no aprobó la cancelación: {_detalle_sifen(codigo, mensaje)}'

    documento.estado = ESTADO_CANCELADO
    documento.motivo_cancelacion = motivo
    documento.xml_cancelacion = xml_evento
    documento.fecha_cancelado = datetime.utcnow()
    documento.respuesta_codigo = str(codigo) if codigo is not None else documento.respuesta_codigo
    documento.respuesta_mensaje = str(mensaje) if mensaje is not None else documento.respuesta_mensaje
    documento.respuesta_raw = _serializar_respuesta(respuesta)
    db.session.commit()
    return documento, None


def inutilizar_documento(documento, motivo):
    """Informa a SIFEN que el número de este documento no se va a usar.

    Es el caso del número **quemado**: se reservó el correlativo al generar el
    DE, y ese DE nunca llegó a SIFEN (se cortó la luz, falló la firma, se anuló
    la venta antes de transmitir). El número ya salió de la secuencia, y si
    nadie avisa, el timbrado queda con un hueco que ante SIFEN no tiene
    explicación.

    No es una cancelación y no se puede reemplazar por una: cancelar necesita
    un CDC aprobado del otro lado. Acá no hay nada que dar de baja, porque
    SIFEN nunca vio el documento.

    Se informa **un número por evento** (`desde` == `hasta`). Agrupar rangos
    sería más barato en llamadas, pero los huecos no son contiguos salvo por
    casualidad, y un rango que abarque un número emitido al medio lo estaría
    inutilizando sin que nadie lo pida.
    """
    error_numero = error_numero_no_inutilizable(documento)
    if error_numero:
        return documento, error_numero

    motivo = (motivo or '').strip()
    error_motivo = error_motivo_inutilizacion(motivo)
    if error_motivo:
        return documento, error_motivo

    config = obtener_configuracion()
    if not config.cert_path:
        return documento, 'Falta cargar el certificado digital (.p12) en la configuración.'

    # xmlgen exige exactamente 8 caracteres y tira un Error genérico; se
    # valida antes para poder decir cuál es el problema.
    timbrado = (documento.timbrado or config.timbrado_numero or '').strip()
    error_timbrado = error_timbrado_inutilizacion(timbrado)
    if error_timbrado:
        return documento, error_timbrado

    numero = int(documento.numero)
    params = construir_params_emisor(config)
    data = {
        'timbrado': timbrado,
        'establecimiento': documento.establecimiento,
        'punto': documento.punto,
        'desde': numero,
        'hasta': numero,
        'tipoDocumento': documento.tipo_documento or TIPO_FACTURA,
        'motivo': motivo,
    }
    respuesta, xml_evento, error = inutilizar_de(
        params, data, config.cert_path,
        descifrar(config.cert_password or ''), _ambiente_setapi(config),
        request_id=documento.id, fecha_firma=_fecha_firma_evento(),
    )
    if error:
        return documento, error

    estado, codigo, mensaje, _protocolo = _interpretar_respuesta(respuesta)
    # `xml_cancelacion` y `motivo_cancelacion` guardan el evento, sea cual sea:
    # un DE tiene a lo sumo uno de los dos (o se transmitió y se cancela, o no
    # se transmitió y se inutiliza), y columnas nuevas obligan a un ALTER en
    # cada instalación a cambio de nada.
    documento.respuesta_codigo = str(codigo) if codigo is not None else documento.respuesta_codigo
    documento.respuesta_mensaje = str(mensaje) if mensaje is not None else documento.respuesta_mensaje
    documento.respuesta_raw = _serializar_respuesta(respuesta)
    documento.xml_cancelacion = xml_evento
    if estado != ESTADO_APROBADO:
        db.session.commit()
        return documento, (
            f'SIFEN no aprobó la inutilización: {_detalle_sifen(codigo, mensaje)}'
        )

    documento.estado = ESTADO_INUTILIZADO
    documento.motivo_cancelacion = motivo
    documento.fecha_cancelado = datetime.utcnow()
    db.session.commit()
    return documento, None
