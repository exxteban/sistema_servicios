"""Alertas de cobertura de stock conectadas al menu gastronomico."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func

from app import db
from app.models.producto import Producto
from app.utils.helpers import utc_bounds_for_local_dates
from gastronomia.models import GastronomiaPedidoItem, GastronomiaPedidoItemModificador, GastronomiaPedidoPago, GastronomiaProducto
from gastronomia.stock_models import GastronomiaOpcionInsumo, GastronomiaRecetaInsumo


DIAS_COBERTURA_ALERTA = 7


def alertas_stock_menu(cliente_id: int, periodo: dict, limite: int = 6) -> list[dict]:
    dias_periodo = _dias_periodo(periodo)
    ventas_producto = _ventas_producto(cliente_id, periodo)
    if not ventas_producto:
        return []

    alertas = _alertas_insumos(cliente_id, ventas_producto, dias_periodo, periodo)
    alertas.extend(_alertas_producto_directo(cliente_id, ventas_producto, dias_periodo))
    alertas.sort(key=lambda item: (item['dias_cobertura_sort'], item['stock_actual'], item['nombre'].lower()))
    return alertas[:max(1, min(20, int(limite or 6)))]


def _ventas_producto(cliente_id: int, periodo: dict) -> dict[int, dict]:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    filas = (
        db.session.query(
            GastronomiaPedidoItem.producto_id,
            GastronomiaPedidoItem.nombre_producto,
            func.coalesce(func.sum(GastronomiaPedidoItem.cantidad), 0).label('cantidad'),
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
    return {
        int(producto_id): {
            'nombre': nombre,
            'cantidad': int(cantidad or 0),
        }
        for producto_id, nombre, cantidad in filas
        if int(cantidad or 0) > 0
    }


def _alertas_insumos(cliente_id: int, ventas_producto: dict[int, dict], dias_periodo: int, periodo: dict) -> list[dict]:
    producto_ids = list(ventas_producto.keys())
    recetas = (
        db.session.query(GastronomiaRecetaInsumo, Producto)
        .join(Producto, Producto.id_producto == GastronomiaRecetaInsumo.insumo_id)
        .filter(
            GastronomiaRecetaInsumo.cliente_id == int(cliente_id),
            GastronomiaRecetaInsumo.producto_id.in_(producto_ids),
            GastronomiaRecetaInsumo.activo.is_(True),
        )
        .all()
    )
    consumo_por_insumo = defaultdict(lambda: {'cantidad': 0, 'productos': set(), 'insumo': None})
    for receta, insumo in recetas:
        venta = ventas_producto.get(int(receta.producto_id))
        if not venta:
            continue
        cantidad_consumida = int(receta.cantidad or 0) * int(venta['cantidad'] or 0)
        if cantidad_consumida <= 0:
            continue
        item = consumo_por_insumo[int(receta.insumo_id)]
        item['cantidad'] += cantidad_consumida
        item['productos'].add(venta['nombre'])
        item['insumo'] = insumo

    for ajuste, item_pedido, insumo in _consumos_opciones(cliente_id, producto_ids, periodo):
        cantidad_consumida = int(ajuste.cantidad_delta or 0) * int(item_pedido.cantidad or 0)
        if cantidad_consumida <= 0:
            continue
        item = consumo_por_insumo[int(ajuste.insumo_id)]
        item['cantidad'] += cantidad_consumida
        item['productos'].add(item_pedido.nombre_producto)
        item['insumo'] = insumo

    alertas = []
    for item in consumo_por_insumo.values():
        insumo = item['insumo']
        if not insumo:
            continue
        alerta = _construir_alerta(
            nombre=insumo.nombre,
            tipo='insumo',
            stock_actual=int(insumo.stock_actual or 0),
            unidad=getattr(insumo, 'unidad_stock', None) or 'unidad',
            consumo_periodo=int(item['cantidad'] or 0),
            dias_periodo=dias_periodo,
            productos=sorted(item['productos'])[:3],
        )
        if alerta:
            alertas.append(alerta)
    return alertas


def _consumos_opciones(cliente_id: int, producto_ids: list[int], periodo: dict):
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    return (
        db.session.query(GastronomiaOpcionInsumo, GastronomiaPedidoItem, Producto)
        .join(
            GastronomiaPedidoItemModificador,
            GastronomiaPedidoItemModificador.opcion_id == GastronomiaOpcionInsumo.opcion_id,
        )
        .join(GastronomiaPedidoItem, GastronomiaPedidoItem.id_item == GastronomiaPedidoItemModificador.item_id)
        .join(GastronomiaPedidoPago, GastronomiaPedidoPago.pedido_id == GastronomiaPedidoItem.pedido_id)
        .join(Producto, Producto.id_producto == GastronomiaOpcionInsumo.insumo_id)
        .filter(
            GastronomiaOpcionInsumo.cliente_id == int(cliente_id),
            GastronomiaOpcionInsumo.activo.is_(True),
            GastronomiaPedidoItemModificador.cliente_id == int(cliente_id),
            GastronomiaPedidoItem.cliente_id == int(cliente_id),
            GastronomiaPedidoItem.producto_id.in_(producto_ids),
            GastronomiaPedidoPago.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .all()
    )


def _alertas_producto_directo(cliente_id: int, ventas_producto: dict[int, dict], dias_periodo: int) -> list[dict]:
    producto_ids = list(ventas_producto.keys())
    productos = GastronomiaProducto.query.filter(
        GastronomiaProducto.cliente_id == int(cliente_id),
        GastronomiaProducto.id_producto.in_(producto_ids),
        GastronomiaProducto.control_stock_venta.is_(True),
    ).all()
    alertas = []
    for producto in productos:
        venta = ventas_producto.get(int(producto.id_producto), {})
        alerta = _construir_alerta(
            nombre=producto.nombre,
            tipo='producto_menu',
            stock_actual=int(producto.stock_disponible or 0),
            unidad='unidad',
            consumo_periodo=int(venta.get('cantidad') or 0),
            dias_periodo=dias_periodo,
            productos=[producto.nombre],
        )
        if alerta:
            alertas.append(alerta)
    return alertas


def _construir_alerta(*, nombre: str, tipo: str, stock_actual: int, unidad: str, consumo_periodo: int, dias_periodo: int, productos: list[str]) -> dict | None:
    consumo_diario = consumo_periodo / max(1, dias_periodo)
    if consumo_diario <= 0:
        return None
    dias_cobertura = stock_actual / consumo_diario if stock_actual > 0 else 0
    if dias_cobertura > DIAS_COBERTURA_ALERTA:
        return None
    dias_label = 'menos de 1 dia' if dias_cobertura < 1 else f'{dias_cobertura:.1f} dias'
    productos_label = ', '.join(productos) if productos else 'el menu actual'
    return {
        'tipo': tipo,
        'nombre': nombre,
        'stock_actual': stock_actual,
        'unidad_stock': unidad,
        'consumo_periodo': consumo_periodo,
        'consumo_diario': round(consumo_diario, 1),
        'dias_cobertura': round(dias_cobertura, 1),
        'dias_cobertura_sort': round(dias_cobertura, 3),
        'dias_cobertura_label': dias_label,
        'productos_label': productos_label,
        'mensaje': f'Si se sigue vendiendo asi, {nombre} dura {dias_label}.',
        'accion': f'Reponer {nombre} o limitar productos como {productos_label}.',
    }


def _dias_periodo(periodo: dict) -> int:
    return max((periodo['hasta'] - periodo['desde']).days + 1, 1)
