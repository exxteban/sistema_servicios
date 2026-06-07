"""Margen estimado por receta para decisiones del menu gastronomico."""
from __future__ import annotations

from sqlalchemy import func

from app import db
from app.models.producto import Producto
from app.utils.helpers import utc_bounds_for_local_dates
from gastronomia.models import GastronomiaPedidoItem, GastronomiaPedidoPago
from gastronomia.stock_models import GastronomiaRecetaInsumo


MARGEN_BAJO_PCT = 35


def productos_alto_volumen_bajo_margen(cliente_id: int, periodo: dict, limite: int = 6) -> list[dict]:
    ventas = _ventas_producto(cliente_id, periodo)
    if not ventas:
        return []

    costos_unitarios = _costos_unitarios_receta(cliente_id, [item['producto_id'] for item in ventas])
    promedio_unidades = sum(item['cantidad'] for item in ventas) / max(len(ventas), 1)
    umbral_volumen = max(3, promedio_unidades)
    candidatos = []

    for venta in ventas:
        costo_unitario = costos_unitarios.get(venta['producto_id'], 0.0)
        if costo_unitario <= 0 or venta['cantidad'] < umbral_volumen:
            continue
        costo_total = costo_unitario * venta['cantidad']
        margen = venta['total'] - costo_total
        margen_pct = (margen / venta['total'] * 100) if venta['total'] > 0 else 0
        if margen_pct > MARGEN_BAJO_PCT:
            continue
        candidatos.append(_serializar_producto(venta, costo_unitario, costo_total, margen, margen_pct))

    candidatos.sort(key=lambda item: (item['margen_pct'], -item['cantidad'], -item['total']))
    return candidatos[:max(1, min(20, int(limite or 6)))]


def _ventas_producto(cliente_id: int, periodo: dict) -> list[dict]:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    filas = (
        db.session.query(
            GastronomiaPedidoItem.producto_id,
            GastronomiaPedidoItem.nombre_producto,
            func.coalesce(func.sum(GastronomiaPedidoItem.cantidad), 0).label('cantidad'),
            func.coalesce(func.sum(GastronomiaPedidoItem.subtotal), 0).label('total'),
        )
        .join(GastronomiaPedidoPago, GastronomiaPedidoPago.pedido_id == GastronomiaPedidoItem.pedido_id)
        .filter(
            GastronomiaPedidoItem.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .group_by(GastronomiaPedidoItem.producto_id, GastronomiaPedidoItem.nombre_producto)
        .all()
    )
    return [{
        'producto_id': int(producto_id or 0),
        'nombre': nombre or 'Producto',
        'cantidad': int(cantidad or 0),
        'total': float(total or 0),
    } for producto_id, nombre, cantidad, total in filas if int(producto_id or 0) > 0]


def _costos_unitarios_receta(cliente_id: int, producto_ids: list[int]) -> dict[int, float]:
    if not producto_ids:
        return {}
    filas = (
        db.session.query(
            GastronomiaRecetaInsumo.producto_id,
            func.coalesce(func.sum(GastronomiaRecetaInsumo.cantidad * Producto.precio_compra), 0),
        )
        .join(Producto, Producto.id_producto == GastronomiaRecetaInsumo.insumo_id)
        .filter(
            GastronomiaRecetaInsumo.cliente_id == int(cliente_id),
            GastronomiaRecetaInsumo.producto_id.in_(producto_ids),
            GastronomiaRecetaInsumo.activo.is_(True),
        )
        .group_by(GastronomiaRecetaInsumo.producto_id)
        .all()
    )
    return {int(producto_id): float(costo or 0) for producto_id, costo in filas}


def _serializar_producto(venta: dict, costo_unitario: float, costo_total: float, margen: float, margen_pct: float) -> dict:
    return {
        **venta,
        'costo_unitario': round(costo_unitario, 2),
        'costo_total': round(costo_total, 2),
        'margen': round(margen, 2),
        'margen_pct': round(margen_pct, 1),
        'total_label': _formatear_moneda(venta['total']),
        'costo_total_label': _formatear_moneda(costo_total),
        'margen_label': _formatear_moneda(margen),
        'margen_pct_label': f'{margen_pct:.1f}%',
        'accion': 'Revisar precio, porcion o costo de receta: vende bien pero deja poco margen.',
    }


def _formatear_moneda(valor: float) -> str:
    return f'₲ {float(valor or 0):,.0f}'.replace(',', '.')
