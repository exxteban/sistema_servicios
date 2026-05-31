"""Previsualizacion no bloqueante del stock para el carrito gastronomico."""
from __future__ import annotations

from collections import Counter

from app.models.producto import Producto
from gastronomia.models import GastronomiaGrupoOpciones, GastronomiaOpcionProducto, GastronomiaProducto
from gastronomia.stock_models import GastronomiaOpcionInsumo, GastronomiaRecetaInsumo


def previsualizar_stock_carrito(cliente_id: int, items: list[dict]) -> list[dict]:
    """Calcula alertas del carrito sin modificar inventario."""
    items = [item for item in items if isinstance(item, dict)]
    requeridos_insumo = Counter()
    requeridos_menu = Counter()
    productos_menu = _productos_menu(cliente_id, items)
    productos_con_receta = set()
    nombres_sin_receta = set()

    for item in items:
        producto_id = _int_positivo(item.get('producto_id') or item.get('id_producto'))
        cantidad = max(1, _int_positivo(item.get('cantidad'), 1))
        producto = productos_menu.get(producto_id)
        if not producto:
            continue
        if producto.control_stock_venta:
            requeridos_menu[producto_id] += cantidad
        receta = _cantidades_receta(cliente_id, producto_id, cantidad, item.get('opciones') or [])
        if receta:
            productos_con_receta.add(producto_id)
            requeridos_insumo.update(receta)
        elif not producto.control_stock_venta:
            nombres_sin_receta.add((producto_id, producto.nombre))

    alertas = []
    for producto_id, cantidad in requeridos_menu.items():
        producto = productos_menu[producto_id]
        _agregar_alerta_faltante(
            alertas,
            tipo_origen='producto_menu',
            nombre=producto.nombre,
            cantidad=cantidad,
            stock_actual=int(producto.stock_disponible or 0),
        )
    if requeridos_insumo:
        insumos = {
            int(item.id_producto): item
            for item in Producto.query.filter(Producto.id_producto.in_(requeridos_insumo)).all()
        }
        for insumo_id, cantidad in requeridos_insumo.items():
            insumo = insumos.get(insumo_id)
            if insumo:
                _agregar_alerta_faltante(
                    alertas,
                    tipo_origen='receta',
                    nombre=insumo.nombre,
                    cantidad=cantidad,
                    stock_actual=int(insumo.stock_actual or 0),
                )
    for producto_id, nombre in sorted(nombres_sin_receta):
        if producto_id not in productos_con_receta:
            alertas.append({
                'producto_id': producto_id,
                'tipo_origen': 'sin_receta',
                'nombre': nombre,
                'mensaje': f'"{nombre}" no tiene receta de stock configurada.',
            })
    return alertas


def _productos_menu(cliente_id: int, items: list[dict]) -> dict[int, GastronomiaProducto]:
    ids = {
        _int_positivo(item.get('producto_id') or item.get('id_producto'))
        for item in items
    }
    ids.discard(0)
    if not ids:
        return {}
    return {
        int(item.id_producto): item
        for item in GastronomiaProducto.query.filter(
            GastronomiaProducto.cliente_id == int(cliente_id),
            GastronomiaProducto.id_producto.in_(ids),
            GastronomiaProducto.activo.is_(True),
        ).all()
    }


def _cantidades_receta(cliente_id: int, producto_id: int, cantidad: int, opciones) -> Counter:
    cantidades = Counter({
        int(item.insumo_id): int(item.cantidad or 0) * cantidad
        for item in GastronomiaRecetaInsumo.query.filter_by(
            cliente_id=int(cliente_id),
            producto_id=int(producto_id),
            activo=True,
        ).all()
    })
    opcion_ids = {_int_positivo(item) for item in opciones} if isinstance(opciones, (list, tuple, set)) else set()
    opcion_ids.discard(0)
    if opcion_ids:
        for ajuste in GastronomiaOpcionInsumo.query.join(
            GastronomiaOpcionProducto,
            GastronomiaOpcionProducto.id_opcion == GastronomiaOpcionInsumo.opcion_id,
        ).join(
            GastronomiaGrupoOpciones,
            GastronomiaGrupoOpciones.id_grupo == GastronomiaOpcionProducto.grupo_id,
        ).filter(
            GastronomiaOpcionInsumo.cliente_id == int(cliente_id),
            GastronomiaOpcionInsumo.opcion_id.in_(opcion_ids),
            GastronomiaOpcionInsumo.activo.is_(True),
            GastronomiaGrupoOpciones.producto_id == int(producto_id),
        ).all():
            cantidades[int(ajuste.insumo_id)] += int(ajuste.cantidad_delta or 0) * cantidad
    return Counter({key: value for key, value in cantidades.items() if value > 0})


def _agregar_alerta_faltante(alertas: list[dict], *, tipo_origen: str, nombre: str, cantidad: int, stock_actual: int):
    faltante = max(0, int(cantidad) - int(stock_actual))
    if not faltante:
        return
    alertas.append({
        'tipo_origen': tipo_origen,
        'nombre': nombre,
        'cantidad': int(cantidad),
        'stock_actual': int(stock_actual),
        'faltante': faltante,
        'mensaje': f'Stock insuficiente de "{nombre}": requiere {cantidad}, disponible {stock_actual}.',
    })


def _int_positivo(value, default=0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
