"""Respuestas idempotentes y registro de ventas descartadas para la cola local del POS.

Este módulo centraliza las respuestas que permiten a la cola offline del POS
resolver de forma segura una venta que ya no debe reintentarse:

- ``_venta_existente_response``: la venta ya fue registrada (mismo client_request_id).
- ``_venta_descartada_response``: la venta fue rechazada de forma permanente en el
  servidor (payload inválido, pendiente ya no disponible, etc.). La cola la puede
  quitar sin dejarla trabada como "requiere revisión".

Se mantiene un registro en memoria (por proceso) de los ``client_request_id``
descartados con un TTL, para que un reintento posterior pueda consultarlo vía
``/ventas/sync-status`` y limpiar la cola local automáticamente.
"""
from time import time


_VENTAS_DESCARTADAS_TTL_SECONDS = 60 * 60
_VENTAS_DESCARTADAS_MAX = 512
_ventas_descartadas_por_request_id = {}


def _limpiar_ventas_descartadas(ahora=None):
    ahora = time() if ahora is None else ahora
    vencimiento = ahora - _VENTAS_DESCARTADAS_TTL_SECONDS
    for request_id, data in list(_ventas_descartadas_por_request_id.items()):
        if float(data.get('ts') or 0) < vencimiento:
            _ventas_descartadas_por_request_id.pop(request_id, None)
    while len(_ventas_descartadas_por_request_id) > _VENTAS_DESCARTADAS_MAX:
        mas_viejo = min(
            _ventas_descartadas_por_request_id,
            key=lambda key: float(_ventas_descartadas_por_request_id[key].get('ts') or 0),
        )
        _ventas_descartadas_por_request_id.pop(mas_viejo, None)


def _registrar_venta_descartada(client_request_id, motivo='payload_invalido'):
    request_id = str(client_request_id or '').strip()
    if not request_id or len(request_id) > 64:
        return
    ahora = time()
    _limpiar_ventas_descartadas(ahora)
    _ventas_descartadas_por_request_id[request_id] = {'motivo': motivo, 'ts': ahora}


def _venta_descartada_response(client_request_id):
    request_id = str(client_request_id or '').strip()
    if not request_id:
        return None
    _limpiar_ventas_descartadas()
    data = _ventas_descartadas_por_request_id.get(request_id)
    if not data:
        return None
    return {
        'success': True,
        'exists': True,
        'source': 'descartada',
        'estado': 'descartada',
        'total': 0,
        'motivo': data.get('motivo') or 'payload_invalido',
    }


def _venta_existente_response(venta):
    total_pagado = sum(float(p.monto) for p in venta.pagos.all())
    total = float(venta.total or 0)
    vuelto = max(0, total_pagado - total)
    return {
        'success': True,
        'id_venta': venta.id_venta,
        'total': total,
        'pagado': total_pagado,
        'vuelto': float(vuelto),
        'mensaje': f'Venta #{venta.id_venta} ya estaba registrada'
    }
