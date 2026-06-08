"""Gestion de pedidos recibidos desde la tienda online."""
from __future__ import annotations

from urllib.parse import quote

from gastronomia.models import GastronomiaPedido
from gastronomia.services.pedido_service import enviar_pedido_cocina, obtener_pedido, serializar_pedidos


def listar_pedidos_tienda(cliente_id: int, *, solo_pendientes: bool = True) -> list[GastronomiaPedido]:
    query = GastronomiaPedido.query.filter(
        GastronomiaPedido.cliente_id == int(cliente_id),
        GastronomiaPedido.origen_pedido == 'tienda_online',
    )
    if solo_pendientes:
        query = query.filter(GastronomiaPedido.estado == 'abierto')
    return query.order_by(GastronomiaPedido.fecha_creacion.desc(), GastronomiaPedido.id_pedido.desc()).all()


def contar_pedidos_tienda_pendientes(cliente_id: int | None) -> int:
    if not cliente_id:
        return 0
    return int(
        GastronomiaPedido.query.filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.origen_pedido == 'tienda_online',
            GastronomiaPedido.estado == 'abierto',
        ).count()
    )


def confirmar_pedido_tienda(cliente_id: int, pedido_id: int) -> GastronomiaPedido:
    pedido = obtener_pedido(cliente_id, pedido_id)
    if not pedido or pedido.origen_pedido != 'tienda_online':
        raise ValueError('Pedido de tienda no encontrado.')
    if pedido.estado != 'abierto':
        raise ValueError('Solo se pueden confirmar pedidos de tienda pendientes.')
    return enviar_pedido_cocina(cliente_id, pedido_id)


def serializar_pedidos_tienda(pedidos: list[GastronomiaPedido]) -> list[dict]:
    data = serializar_pedidos(pedidos)
    for pedido in data:
        telefono = ''.join(ch for ch in str(pedido.get('celular_cliente') or '') if ch.isdigit())
        pedido['whatsapp_cliente_url'] = _whatsapp_cliente_url(telefono, pedido)
    return data


def _whatsapp_cliente_url(telefono: str, pedido: dict) -> str | None:
    if not telefono:
        return None
    codigo = pedido.get('codigo_entrega') or f"#{pedido.get('id_pedido')}"
    mensaje = f"Hola, recibimos tu pedido {codigo}. Te contactamos para confirmar disponibilidad y tiempo de entrega."
    return f'https://wa.me/{telefono}?text={quote(mensaje)}'
