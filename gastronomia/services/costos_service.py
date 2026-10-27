"""Costo estimado por plato: insumos de receta (precio de compra) + costo extra fijo."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app import db
from app.models.producto import Producto
from gastronomia.models import GastronomiaProducto
from gastronomia.services.inteligencia_margen import costos_unitarios_receta
from gastronomia.services.stock_service import _obtener_insumo, _obtener_producto_menu
from gastronomia.stock_models import GastronomiaRecetaInsumo


def costo_plato(cliente_id: int, producto_id: int) -> dict:
    """Desglose del costo de un plato para la pantalla de recetas."""
    producto = _obtener_producto_menu(cliente_id, producto_id)
    receta = (
        GastronomiaRecetaInsumo.query
        .filter_by(cliente_id=int(cliente_id), producto_id=int(producto.id_producto), activo=True)
        .order_by(GastronomiaRecetaInsumo.id_receta_insumo.asc())
        .all()
    )
    insumos = []
    for fila in receta:
        precio = float(getattr(fila.insumo, 'precio_compra', 0) or 0)
        insumos.append({
            'insumo_id': int(fila.insumo_id),
            'insumo_nombre': fila.insumo.nombre if fila.insumo else '',
            'cantidad': int(fila.cantidad or 0),
            'unidad_stock': getattr(fila.insumo, 'unidad_stock', 'unidad') or 'unidad',
            'precio_compra': precio,
            'subtotal': precio * int(fila.cantidad or 0),
        })
    costo_insumos = sum(item['subtotal'] for item in insumos)
    return {
        **_resumen_costo(producto, costo_insumos),
        'insumos': insumos,
        'insumos_sin_precio': sum(1 for item in insumos if item['precio_compra'] <= 0),
    }


def resumen_costos_platos(cliente_id: int) -> list[dict]:
    """Costo y ganancia por plato activo, para la lista de recetas."""
    productos = GastronomiaProducto.query.filter_by(cliente_id=int(cliente_id), activo=True).all()
    costos = costos_unitarios_receta(cliente_id, [int(p.id_producto) for p in productos])
    return [_resumen_costo(p, costos.get(int(p.id_producto), 0.0)) for p in productos]


def costo_total_por_plato(cliente_id: int, producto_ids: list[int]) -> dict[int, float]:
    """Costo unitario estimado (receta + extra) por producto del menu."""
    if not producto_ids:
        return {}
    costos = costos_unitarios_receta(cliente_id, producto_ids)
    extras = dict(
        db.session.query(GastronomiaProducto.id_producto, GastronomiaProducto.costo_extra)
        .filter(
            GastronomiaProducto.cliente_id == int(cliente_id),
            GastronomiaProducto.id_producto.in_(producto_ids),
        )
        .all()
    )
    return {
        int(pid): costos.get(int(pid), 0.0) + float(extras.get(int(pid)) or 0)
        for pid in producto_ids
    }


def guardar_costo_extra(cliente_id: int, producto_id: int, monto) -> dict:
    producto = _obtener_producto_menu(cliente_id, producto_id)
    producto.costo_extra = _parse_monto(monto)
    db.session.commit()
    return costo_plato(cliente_id, producto.id_producto)


def aplicar_costo_extra_categoria(cliente_id: int, producto_id: int, monto) -> int:
    """Copia el costo extra a todos los platos activos de la misma categoria."""
    producto = _obtener_producto_menu(cliente_id, producto_id)
    valor = _parse_monto(monto)
    actualizados = (
        GastronomiaProducto.query
        .filter_by(cliente_id=int(cliente_id), categoria_id=int(producto.categoria_id), activo=True)
        .update({GastronomiaProducto.costo_extra: valor}, synchronize_session=False)
    )
    db.session.commit()
    return int(actualizados or 0)


def guardar_precio_compra_insumo(cliente_id: int, insumo_id: int, monto) -> Producto:
    insumo = _obtener_insumo(cliente_id, insumo_id)
    insumo.precio_compra = _parse_monto(monto)
    db.session.commit()
    return insumo


def _resumen_costo(producto: GastronomiaProducto, costo_insumos: float) -> dict:
    costo_extra = float(producto.costo_extra or 0)
    costo_total = costo_insumos + costo_extra
    precio = float(producto.precio or 0)
    ganancia = precio - costo_total
    return {
        'producto_id': int(producto.id_producto),
        'producto_nombre': producto.nombre,
        'precio': precio,
        'costo_insumos': round(costo_insumos, 2),
        'costo_extra': round(costo_extra, 2),
        'costo_total': round(costo_total, 2),
        'ganancia': round(ganancia, 2),
        'ganancia_pct': round(ganancia / precio * 100, 1) if precio > 0 else 0.0,
        'tiene_costo': costo_total > 0,
    }


def _parse_monto(value) -> Decimal:
    texto = str(value if value is not None else '').strip()
    if not texto:
        return Decimal('0')
    try:
        monto = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError('Monto invalido.') from exc
    if not monto.is_finite():
        raise ValueError('Monto invalido.')
    if monto < 0:
        raise ValueError('El monto no puede ser negativo.')
    return monto
