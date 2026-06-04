"""Serializacion limitada a los datos operativos visibles en cocina."""
from __future__ import annotations

from gastronomia.services.pedido_service import serializar_pedidos


_CLAVES_PRIVADAS_COCINA = {
    'alertas_stock',
    'costo_envio',
    'descuento_linea',
    'descuento_monto',
    'estado_pago',
    'pago',
    'precio',
    'precio_delta',
    'precio_original',
    'precio_unitario',
    'subtotal',
    'total',
    'total_cobrado',
}


def serializar_pedidos_cocina(pedidos) -> list[dict]:
    return [_normalizar_pedido_cocina(_sin_datos_privados(item)) for item in serializar_pedidos(pedidos)]


def serializar_eventos_cocina(eventos) -> list[dict]:
    return [_normalizar_evento_cocina(_sin_datos_privados(evento.to_dict())) for evento in eventos]


def _sin_datos_privados(value):
    if isinstance(value, list):
        return [_sin_datos_privados(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _sin_datos_privados(item)
        for key, item in value.items()
        if key not in _CLAVES_PRIVADAS_COCINA
    }


def _normalizar_pedido_cocina(pedido: dict) -> dict:
    if pedido.get('tipo_pedido') == 'delivery' and pedido.get('estado') == 'abierto':
        return {**pedido, 'estado': 'enviado_cocina'}
    return pedido


def _normalizar_evento_cocina(evento: dict) -> dict:
    payload = evento.get('payload') if isinstance(evento.get('payload'), dict) else None
    pedido = payload.get('pedido') if payload else None
    if not isinstance(pedido, dict):
        return evento
    return {**evento, 'payload': {**payload, 'pedido': _normalizar_pedido_cocina(pedido)}}
