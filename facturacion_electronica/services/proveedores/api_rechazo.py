"""Motivo de rechazo de un DE: no está en los eventos SIFEN del documento.

`GET /sifen/electronic-documents/{id}/events/` lista cancelación, inutilización
y nominación (`SifenEventReadEventTypeEnum`). El resultado de la emisión vive
en `SifenBatchRead.items[].result`, y el log `GET /events/` apunta al lote
con `batch.processed`.
"""
from app import db
from facturacion_electronica.services.proveedores import api_client

_CLAVES_CODIGO_RECHAZO = ('dCodRes', 'sifen_code', 'code', 'codigo')
_CLAVES_MENSAJE_RECHAZO = ('dMsgRes', 'message', 'mensaje', 'detail', 'error', 'dDesRes')


def _texto_rechazo(resultado):
    """(codigo, mensaje) a partir del `result` de un ítem de lote.

    Busca un nivel más adentro: la respuesta de SIFEN puede venir envuelta
    (`gResProc`, `response`, una lista de resultados por documento).
    """
    if isinstance(resultado, (list, tuple)):
        for elemento in resultado:
            codigo, mensaje = _texto_rechazo(elemento)
            if codigo or mensaje:
                return codigo, mensaje
        return None, None
    if not isinstance(resultado, dict):
        return None, None

    def _primera(claves):
        for clave in claves:
            valor = resultado.get(clave)
            if valor not in (None, ''):
                return str(valor).strip()
        return None

    codigo = _primera(_CLAVES_CODIGO_RECHAZO)
    mensaje = _primera(_CLAVES_MENSAJE_RECHAZO)
    if codigo or mensaje:
        return codigo, mensaje
    for valor in resultado.values():
        if isinstance(valor, (dict, list, tuple)):
            codigo, mensaje = _texto_rechazo(valor)
            if codigo or mensaje:
                return codigo, mensaje
    return None, None


def texto_resultado(resultado):
    """(codigo, mensaje) de un `result` de SIFEN, venga de donde venga.

    El de la emisión llega en el ítem del lote; el de la inutilización, en el
    `SifenEventRead` que devuelve el evento. Es el mismo objeto libre en su
    OpenAPI y se tantea igual, así que se lee con la misma función.
    """
    return _texto_rechazo(resultado)


def _resultado_en_items(items, documento_id):
    documento_id = str(documento_id or '')
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if str(item.get('document_id') or '') != documento_id:
            continue
        resultado = item.get('result')
        if resultado not in (None, {}, []):
            return resultado
    return None


def _resultado_de_lote(config, lote_id, documento_id):
    if not lote_id:
        return None
    datos, error = api_client.solicitar(config, 'GET', f'/sifen/batches/{lote_id}/')
    if error or not isinstance(datos, dict):
        return None
    return _resultado_en_items(datos.get('items'), documento_id)


def _resultado_en_payload(payload, documento_id):
    if not isinstance(payload, dict):
        return None
    hallado = _resultado_en_items(payload.get('items'), documento_id)
    if hallado is not None:
        return hallado
    if str(payload.get('document_id') or '') == str(documento_id or ''):
        resultado = payload.get('result')
        if resultado not in (None, {}, []):
            return resultado
    return None


def _motivo_desde_eventos(config, documento):
    """(lote_id, result) del log de integración. Silencioso si falla."""
    datos, error = api_client.solicitar(config, 'GET', '/events/?limit=200')
    if error or not isinstance(datos, dict):
        return None, None

    documento_id = documento.api_documento_id
    lote_id = None
    resultado = None
    for evento in datos.get('results') or []:
        if not isinstance(evento, dict):
            continue
        if (evento.get('event_type') or '') != 'batch.processed':
            continue
        resource_id = evento.get('resource_id')
        payload = evento.get('payload') if isinstance(evento.get('payload'), dict) else {}
        candidato = _resultado_en_payload(payload, documento_id)
        if candidato is not None:
            resultado = candidato
            lote_id = resource_id or lote_id
            continue
        if resource_id and _payload_apunta_al_documento(payload, documento_id):
            lote_id = resource_id
    return lote_id, resultado


def _payload_apunta_al_documento(payload, documento_id):
    documento_id = str(documento_id or '')
    if not documento_id or not isinstance(payload, dict):
        return False
    for clave in ('document_id', 'id'):
        if str(payload.get(clave) or '') == documento_id:
            return True
    for item in payload.get('items') or []:
        if isinstance(item, dict) and str(item.get('document_id') or '') == documento_id:
            return True
    return False


def _motivo_desde_lotes_recientes(config, documento):
    datos, error = api_client.solicitar(
        config, 'GET', '/sifen/batches/?page_size=20&ordering=-created_at',
    )
    if error or not isinstance(datos, dict):
        return None, None
    documento_id = documento.api_documento_id
    for lote in datos.get('results') or []:
        if not isinstance(lote, dict):
            continue
        lote_id = lote.get('id')
        resultado = _resultado_en_items(lote.get('items'), documento_id)
        if resultado is not None:
            return resultado, lote_id
        if lote_id and not lote.get('items'):
            resultado = _resultado_de_lote(config, lote_id, documento_id)
            if resultado is not None:
                return resultado, lote_id
    return None, None


def completar_motivo_rechazo(config, documento):
    """Trae el porqué del rechazo. Silencioso si falla, como el protocolo y el QR.

    No toca `respuesta_codigo`: ahí va el estado de la API y es lo que lee el
    job para decidir el próximo paso. El código de SIFEN va dentro del mensaje.
    """
    if not documento.api_documento_id:
        return

    resultado = None
    lote_id = documento.api_lote_id
    if lote_id:
        resultado = _resultado_de_lote(config, lote_id, documento.api_documento_id)

    if resultado is None:
        lote_log, resultado_log = _motivo_desde_eventos(config, documento)
        if resultado_log is not None:
            resultado = resultado_log
        if lote_log:
            lote_id = lote_id or lote_log
            if resultado is None:
                resultado = _resultado_de_lote(config, lote_log, documento.api_documento_id)

    if resultado is None:
        resultado, lote_lista = _motivo_desde_lotes_recientes(config, documento)
        lote_id = lote_id or lote_lista

    if lote_id and lote_id != documento.api_lote_id:
        documento.api_lote_id = str(lote_id)[:36]

    if resultado is None:
        return
    codigo, mensaje = _texto_rechazo(resultado)
    if not (codigo or mensaje):
        return
    detalle = ' - '.join(parte for parte in (codigo, mensaje) if parte)
    documento.respuesta_mensaje = f'Rechazado por SIFEN: {detalle}'[:2000]
    db.session.commit()


__all__ = ['completar_motivo_rechazo', 'texto_resultado']
