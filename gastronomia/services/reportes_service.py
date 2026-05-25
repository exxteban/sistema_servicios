"""Metricas iniciales para reportes de Gastronomia."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func

from app import db
from app.utils.helpers import parse_iso_date, today_local, utc_bounds_for_local_dates
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem, GastronomiaPedidoPago


def resumen_reportes(cliente_id: int, fecha_desde: str | None = None, fecha_hasta: str | None = None) -> dict:
    inicio, fin = _periodo(fecha_desde, fecha_hasta)
    pagos = _pagos_periodo(cliente_id, inicio, fin).all()
    pedidos_cobrados = len(pagos)
    ventas_total = sum(float(pago.total_cobrado or 0) for pago in pagos)
    descuentos_total = sum(float(pago.descuento_monto or 0) for pago in pagos)
    return {
        'periodo': {
            'desde': inicio.date().isoformat(),
            'hasta': (fin - timedelta(days=1)).date().isoformat(),
        },
        'ventas_total': ventas_total,
        'descuentos_total': descuentos_total,
        'pedidos_cobrados': pedidos_cobrados,
        'ticket_promedio': ventas_total / pedidos_cobrados if pedidos_cobrados else 0,
        'ventas_por_metodo': ventas_por_metodo(cliente_id, inicio, fin),
        'productos_mas_vendidos': productos_mas_vendidos(cliente_id, inicio, fin),
        'tiempo_promedio_preparacion_min': tiempo_promedio_preparacion(cliente_id, inicio, fin),
        'pedidos_cancelados': pedidos_cancelados(cliente_id, inicio, fin),
    }


def ventas_por_metodo(cliente_id: int, inicio: datetime, fin: datetime) -> list[dict]:
    filas = (
        _pagos_periodo(cliente_id, inicio, fin)
        .with_entities(
            GastronomiaPedidoPago.metodo_pago,
            func.count(GastronomiaPedidoPago.id_pago),
            func.coalesce(func.sum(GastronomiaPedidoPago.total_cobrado), 0),
        )
        .group_by(GastronomiaPedidoPago.metodo_pago)
        .order_by(func.sum(GastronomiaPedidoPago.total_cobrado).desc())
        .all()
    )
    return [
        {'metodo_pago': metodo, 'cantidad': int(cantidad or 0), 'total': float(total or 0)}
        for metodo, cantidad, total in filas
    ]


def productos_mas_vendidos(cliente_id: int, inicio: datetime, fin: datetime, limite: int = 10) -> list[dict]:
    filas = (
        db.session.query(
            GastronomiaPedidoItem.producto_id,
            GastronomiaPedidoItem.nombre_producto,
            func.coalesce(func.sum(GastronomiaPedidoItem.cantidad), 0).label('cantidad'),
            func.coalesce(func.sum(GastronomiaPedidoItem.subtotal), 0).label('total'),
        )
        .join(GastronomiaPedido, GastronomiaPedido.id_pedido == GastronomiaPedidoItem.pedido_id)
        .join(GastronomiaPedidoPago, GastronomiaPedidoPago.pedido_id == GastronomiaPedido.id_pedido)
        .filter(
            GastronomiaPedidoItem.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .group_by(GastronomiaPedidoItem.producto_id, GastronomiaPedidoItem.nombre_producto)
        .order_by(func.sum(GastronomiaPedidoItem.cantidad).desc())
        .limit(max(1, min(50, int(limite or 10))))
        .all()
    )
    return [
        {
            'producto_id': producto_id,
            'nombre_producto': nombre,
            'cantidad': int(cantidad or 0),
            'total': float(total or 0),
        }
        for producto_id, nombre, cantidad, total in filas
    ]


def tiempo_promedio_preparacion(cliente_id: int, inicio: datetime, fin: datetime) -> float:
    pedidos = (
        GastronomiaPedido.query
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.fecha_listo >= inicio,
            GastronomiaPedido.fecha_listo < fin,
            GastronomiaPedido.fecha_envio_cocina.isnot(None),
            GastronomiaPedido.fecha_listo.isnot(None),
        )
        .all()
    )
    minutos = [
        max(0, (pedido.fecha_listo - pedido.fecha_envio_cocina).total_seconds() / 60)
        for pedido in pedidos
    ]
    return round(sum(minutos) / len(minutos), 2) if minutos else 0


def pedidos_cancelados(cliente_id: int, inicio: datetime, fin: datetime) -> int:
    return (
        GastronomiaPedido.query
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.estado == 'cancelado',
            GastronomiaPedido.fecha_creacion >= inicio,
            GastronomiaPedido.fecha_creacion < fin,
        )
        .count()
    )


def _pagos_periodo(cliente_id: int, inicio: datetime, fin: datetime):
    return GastronomiaPedidoPago.query.filter(
        GastronomiaPedidoPago.cliente_id == int(cliente_id),
        GastronomiaPedidoPago.fecha_pago >= inicio,
        GastronomiaPedidoPago.fecha_pago < fin,
    )


def _periodo(fecha_desde: str | None, fecha_hasta: str | None) -> tuple[datetime, datetime]:
    desde = parse_iso_date(fecha_desde) or today_local()
    hasta = parse_iso_date(fecha_hasta) or desde
    if hasta < desde:
        hasta = desde
    return utc_bounds_for_local_dates(desde, hasta)
