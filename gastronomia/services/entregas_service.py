"""Consulta y resumen de entregas gastronomicas."""
from __future__ import annotations

import re

from app import db
from app.utils.helpers import parse_iso_date, today_local, utc_bounds_for_local_dates
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem, GastronomiaPedidoPago
from gastronomia.services.pedido_service import ESTADOS_PEDIDO, serializar_pedidos


TIPOS_PEDIDO = {'mesa', 'mostrador', 'retiro'}


def buscar_entregas(cliente_id: int, filtros: dict) -> dict:
    fecha = _fecha_filtro(filtros.get('fecha'))
    inicio, fin = utc_bounds_for_local_dates(fecha, fecha)
    query = (
        GastronomiaPedido.query
        .outerjoin(GastronomiaPedidoPago, GastronomiaPedidoPago.pedido_id == GastronomiaPedido.id_pedido)
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.fecha_entrega.isnot(None),
            GastronomiaPedido.fecha_entrega >= inicio,
            GastronomiaPedido.fecha_entrega < fin,
        )
    )

    estado = (filtros.get('estado') or '').strip().lower()
    if estado in ESTADOS_PEDIDO:
        query = query.filter(GastronomiaPedido.estado == estado)

    tipo_pedido = (filtros.get('tipo_pedido') or '').strip().lower()
    if tipo_pedido in TIPOS_PEDIDO:
        query = query.filter(GastronomiaPedido.tipo_pedido == tipo_pedido)

    pagado = _parse_paid_filter(filtros.get('pagado'))
    if pagado is True:
        query = query.filter(GastronomiaPedidoPago.id_pago.isnot(None))
    elif pagado is False:
        query = query.filter(GastronomiaPedidoPago.id_pago.is_(None))

    query = _apply_search(query, filtros.get('q'))
    pedidos = (
        query
        .order_by(GastronomiaPedido.fecha_entrega.desc(), GastronomiaPedido.id_pedido.desc())
        .all()
    )
    pedidos_data = serializar_pedidos(pedidos)
    return {
        'fecha': fecha.isoformat(),
        'resumen': _resumen(pedidos_data),
        'pedidos': pedidos_data,
    }


def _fecha_filtro(value) -> object:
    text = str(value or '').strip().lower()
    if text in {'', 'hoy', 'today'}:
        return today_local()
    return parse_iso_date(text) or today_local()


def _parse_paid_filter(value) -> bool | None:
    text = str(value or '').strip().lower()
    if text in {'1', 'true', 'si', 'sí', 'pagado'}:
        return True
    if text in {'0', 'false', 'no', 'pendiente'}:
        return False
    return None


def _apply_search(query, value):
    text = str(value or '').strip()
    if not text:
        return query
    like = f'%{text}%'
    conditions = [
        GastronomiaPedido.mesa.ilike(like),
        GastronomiaPedido.referencia_entrega.ilike(like),
        GastronomiaPedido.tipo_pedido.ilike(like),
        GastronomiaPedido.items.any(GastronomiaPedidoItem.nombre_producto.ilike(like)),
    ]
    digits = re.sub(r'\D+', '', text)
    if digits:
        conditions.append(GastronomiaPedido.id_pedido == int(digits))
    return query.filter(db.or_(*conditions))


def _resumen(pedidos: list[dict]) -> dict:
    total_vendido = sum(float(pedido.get('total') or 0) for pedido in pedidos)
    pagados = [pedido for pedido in pedidos if pedido.get('pagado')]
    pendiente_pago = len(pedidos) - len(pagados)
    total_pagado = sum(float(pedido.get('pago', {}).get('total_cobrado') or 0) for pedido in pagados)
    return {
        'cantidad_entregada': len(pedidos),
        'total_vendido': total_vendido,
        'cantidad_pagada': len(pagados),
        'cantidad_pendiente_pago': pendiente_pago,
        'total_pagado': total_pagado,
    }
