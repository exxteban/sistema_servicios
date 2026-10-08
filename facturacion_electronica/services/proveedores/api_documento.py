"""Copia local del documento remoto: estados, QR, protocolo e idempotencia."""
import json
from datetime import datetime

from app import db
from facturacion_electronica import (
    AMBIENTE_PRODUCCION,
    AMBIENTE_TEST,
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_ENVIADO,
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    ESTADO_GENERADO,
    ESTADO_INUTILIZADO,
    ESTADO_RECHAZADO,
)
from facturacion_electronica.services.proveedores import api_client
from facturacion_electronica.services.proveedores.api_payload import referencia_externa
from facturacion_electronica.services.proveedores.api_rechazo import completar_motivo_rechazo

# Estados de la API → estados nuestros. Los que no están (DRAFT, PREPARING)
# significan "todavía no preparado" y se mapean a 'generado'.
ESTADOS_API = {
    'DRAFT': ESTADO_GENERADO,
    'PREPARING': ESTADO_GENERADO,
    # Ya tiene CDC, firma y QR; sólo falta que salga al lote.
    'PENDING_BATCH': ESTADO_FIRMADO,
    'BATCHED': ESTADO_ENVIADO,
    'SUBMITTED': ESTADO_ENVIADO,
    'APPROVED': ESTADO_APROBADO,
    'REJECTED': ESTADO_RECHAZADO,
    'RETRYABLE_ERROR': ESTADO_ERROR,
    # Sigue vigente hasta que SIFEN confirme la cancelación.
    'CANCELLATION_PENDING': ESTADO_APROBADO,
    'CANCELLED': ESTADO_CANCELADO,
    'VOIDED': ESTADO_INUTILIZADO,
}


def serializar(datos):
    try:
        return json.dumps(datos, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(datos)


def ambiente_de_origen(remoto):
    """`origin_mode` del alta: snapshot inmutable del modo al crear el DE."""
    modo = (remoto.get('origin_mode') or '').strip().lower()
    if modo == 'production':
        return AMBIENTE_PRODUCCION
    if modo in ('test', 'sandbox'):
        return AMBIENTE_TEST
    return None


def mensaje_estado(remoto):
    texto = (remoto.get('status_display') or remoto.get('status') or '').strip()
    return texto or None


def aplicar_remoto(documento, remoto, guardar=True):
    """Copia al documento local lo que informó la API. Devuelve el estado nuevo."""
    estado_api = (remoto.get('status') or '').upper()
    estado = ESTADOS_API.get(estado_api, ESTADO_ENVIADO)

    documento.api_documento_id = remoto.get('id') or documento.api_documento_id
    if remoto.get('cdc'):
        documento.cdc = remoto['cdc']
    if remoto.get('qr_url'):
        documento.qr_url = remoto['qr_url']
    ambiente_origen = ambiente_de_origen(remoto)
    if ambiente_origen:
        documento.ambiente = ambiente_origen
    documento.respuesta_codigo = estado_api or documento.respuesta_codigo
    documento.respuesta_mensaje = mensaje_estado(remoto) or documento.respuesta_mensaje
    documento.respuesta_raw = serializar(remoto)
    documento.estado = estado
    if estado in (ESTADO_ENVIADO, ESTADO_APROBADO) and not documento.fecha_envio:
        documento.fecha_envio = datetime.utcnow()
    if estado == ESTADO_CANCELADO and not documento.fecha_cancelado:
        documento.fecha_cancelado = datetime.utcnow()
    if guardar:
        db.session.commit()
    return estado


def completar_protocolo(config, documento):
    """Protocolo de autorización de SIFEN, para el KuDE. Silencioso si falla."""
    if documento.protocolo_autorizacion or not documento.cdc:
        return
    datos, error = api_client.solicitar(config, 'GET', f'/sifen/lookup/cdc/{documento.cdc}/')
    if error or not isinstance(datos, dict):
        return
    protocolo = datos.get('prot_aut')
    if protocolo:
        documento.protocolo_autorizacion = str(protocolo)[:20]
        db.session.commit()


def completar_qr(config, documento):
    """Trae el `qr_url` cuando la respuesta que lo traía se perdió.

    Detalle del contrato que es fácil pasar por alto: el alta (201) responde
    `ElectronicDocumentDetailRead`, que lleva `qr_url`; el GET del documento y
    el listado responden `ElectronicDocumentRead`, que **no lo lleva**. El
    único GET que devuelve el detalle es `by-cdc`.

    Sin esto, un alta cuya respuesta se perdió (corte de red) se adopta por el
    listado y el documento queda sin QR para siempre: el KuDE se imprime sin
    el código y nada lo avisa. Silencioso si falla, como el protocolo.
    """
    if documento.qr_url or not documento.cdc:
        return
    datos, error = api_client.solicitar(
        config, 'GET', f'/sifen/electronic-documents/by-cdc/{documento.cdc}/'
    )
    if error or not isinstance(datos, dict):
        return
    if datos.get('qr_url'):
        documento.qr_url = datos['qr_url']
        db.session.commit()


def adoptar_remoto(config, documento, remoto):
    """`aplicar_remoto` + el QR que el listado no trae. Devuelve el estado."""
    estado = aplicar_remoto(documento, remoto)
    completar_qr(config, documento)
    if estado == ESTADO_RECHAZADO:
        completar_motivo_rechazo(config, documento, remoto)
    return estado


def buscar_remoto(config, documento):
    """Busca en la API un documento ya emitido para esta venta y número.

    Es la red de contención del corte de red a mitad del alta: el POST pudo
    llegar y la respuesta perderse. Sin esto, el reintento emitiría dos veces
    el mismo número (o chocaría contra la clave de idempotencia sin saber por qué).
    """
    if not documento.numero:
        return None, None
    ruta = (
        '/sifen/electronic-documents/'
        f'?external_ref={referencia_externa(documento)}&page_size=50'
    )
    datos, error = api_client.solicitar(config, 'GET', ruta)
    if error:
        return None, error
    clave = clave_idempotencia(documento)
    for remoto in (datos or {}).get('results') or []:
        if (remoto.get('idempotency_key') or '') == clave or _mismo_numero(remoto, documento):
            return remoto, None
    return None, None


def _mismo_numero(remoto, documento):
    """True si el DE remoto es este mismo número fiscal (tipo, local, punto, número).

    El listado no trae el número, pero el CDC sí (posiciones 1-2 tipo, 12-14
    establecimiento, 15-17 punto, 18-24 número). Con el filtro por
    `external_ref`, un DE de esta venta con este número es este documento
    aunque lo hayan dado de alta con otra clave (el proveedor, a mano).
    """
    cdc = str(remoto.get('cdc') or '')
    if len(cdc) != 44 or not documento.numero:
        return False
    return (
        int(cdc[0:2]) == int(documento.tipo_documento or 1)
        and cdc[11:14] == (documento.establecimiento or '')
        and cdc[14:17] == (documento.punto or '')
        and cdc[17:24] == documento.numero
    )


def liberar_numero_tomado(documento, error):
    """Ante `fiscal_number_conflict`, suelta el número para tomar el siguiente.

    El número ya lo tiene OTRO documento en la API (si fuera de esta venta,
    `buscar_remoto` lo habría adoptado antes). Como existe allá, dejarlo no
    abre un hueco en el timbrado, y reintentar con él falla para siempre.
    Sin número ni clave, el próximo intento —el botón o el job— reserva el
    siguiente. Devuelve el mensaje que queda a la vista.
    """
    if 'fiscal_number_conflict' not in (error or '') or documento.api_documento_id:
        return error
    tomado = documento.numero
    documento.numero = None
    documento.api_idempotency_key = None
    return (f'El número {tomado} ya lo tiene otro documento en la API (emitido desde otro '
            'sistema o por el proveedor). El próximo intento usa el número siguiente.')


def bloqueo_entrega_inicial(venta):
    """El crédito con entrega inicial. Devuelve el error, o None.

    El crédito a secas ya se emite (la API sumó `gPagCred` en su 1.1.0), pero
    el crédito **con entrega inicial** sigue bloqueado del otro lado: `entries`
    junto con `condition: "credito"` se rechaza. Mandar la venta como crédito
    puro escondería la plata que el cliente entregó, así que se corta acá, del
    lado nuestro, por las dos razones de siempre: no consumir un correlativo
    que nunca va a salir, y que la pantalla diga por qué en vez de mostrar el
    400 crudo de la API.
    """
    if (getattr(venta, 'tipo_venta', '') or '').strip().lower() != 'credito':
        return None
    entregado = sum(float(pago.monto or 0) for pago in (venta.pagos or []))
    if entregado <= 0:
        return None
    return (
        'La API de facturación electrónica todavía no emite ventas a crédito con entrega '
        'inicial: no acepta declarar el pago entregado junto con el saldo financiado. La '
        'venta quedó registrada; la factura hay que emitirla cuando el proveedor lo '
        'habilite, o cobrarla toda al contado.'
    )


def clave_idempotencia(documento):
    """Estable por documento: el mismo reintento nunca crea un segundo DE.

    Se guarda en el documento porque una re-emisión (DE cancelado → nuevo DE)
    tiene que estrenar clave aunque comparta venta.
    """
    if not documento.api_idempotency_key:
        documento.api_idempotency_key = (
            f'fe-{documento.id_venta}-{documento.establecimiento or "000"}'
            f'-{documento.punto or "000"}-{documento.numero or "0000000"}'
            f'-{documento.codigo_seguridad or "0"}'
        )
    return documento.api_idempotency_key


def transmite(documento):
    """`transmits` de la última respuesta: False = la API no lo va a enviar."""
    try:
        remoto = json.loads(documento.respuesta_raw or '{}')
    except (TypeError, ValueError):
        return True
    return remoto.get('transmits') is not False


MENSAJE_SANDBOX = (
    'La empresa está en modo sandbox en la API: el documento se firmó y quedó '
    'con CDC, pero no se transmite a SIFEN. Pedile al proveedor que pase la '
    'empresa a test o producción. Ojo: ese cambio no destraba a los documentos '
    'que ya se dieron de alta en sandbox —el modo queda fijado al crearlos—, '
    'así que hay que volver a emitirlos después.'
)


def descargar_kude_pdf(config, documento):
    """PDF A4 oficial del proveedor. Devuelve (bytes, error)."""
    if documento is None or not documento.api_documento_id:
        return None, 'El documento todavía no fue dado de alta en la API.'
    return api_client.solicitar(
        config, 'GET', f'/sifen/electronic-documents/{documento.api_documento_id}/kude/',
        binario=True, timeout=api_client.TIMEOUT_EMISION_SEGUNDOS,
    )


def descargar_xml(config, documento):
    """XML firmado del documento, como texto. Devuelve (xml, error)."""
    if documento is None or not documento.api_documento_id:
        return None, 'El documento todavía no fue dado de alta en la API.'
    contenido, error = api_client.solicitar(
        config, 'GET', f'/sifen/electronic-documents/{documento.api_documento_id}/xml/',
        binario=True, timeout=api_client.TIMEOUT_EMISION_SEGUNDOS,
    )
    if error:
        return None, error
    return contenido.decode('utf-8', errors='replace'), None


__all__ = [
    'ESTADOS_API',
    'descargar_kude_pdf',
    'descargar_xml',
    'MENSAJE_SANDBOX',
    'transmite',
    'adoptar_remoto',
    'aplicar_remoto',
    'bloqueo_entrega_inicial',
    'buscar_remoto',
    'clave_idempotencia',
    'liberar_numero_tomado',
    'completar_protocolo',
    'serializar',
]
