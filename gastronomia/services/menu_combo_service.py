"""Armado de combos a partir de productos ya cargados en el menu.

Un combo es un producto mas (categoria "Combos") con precio propio. Si se deja
elegir bebida, se agrega un grupo de opciones tipo `combo` obligatorio.
Para que el stock por recetas siga funcionando, la receta del combo es la suma
de las recetas de sus productos y cada bebida suma su receta como opcion.
"""
from __future__ import annotations

from collections import Counter

from app import db
from gastronomia.models import GastronomiaCategoria, GastronomiaProducto
from gastronomia.services.menu_service import (
    es_categoria_bebida,
    guardar_categoria,
    guardar_producto,
    parse_int,
    parse_price,
)
from gastronomia.services.modificadores_service import guardar_grupo, guardar_opcion
from gastronomia.services.stock_service import guardar_receta
from gastronomia.stock_models import GastronomiaRecetaInsumo


CATEGORIA_COMBOS = 'Combos'
GRUPO_BEBIDA = 'Elegi la bebida'
MAX_PRODUCTOS_COMBO = 10
MAX_BEBIDAS_COMBO = 30


def resumen_productos_para_combo(productos: list[GastronomiaProducto]) -> list[dict]:
    """Datos minimos que usa el modal de promo/combo en el navegador."""
    return [
        {
            'id': int(producto.id_producto),
            'nombre': producto.nombre,
            'precio': float(producto.precio or 0),
            'categoria': producto.categoria.nombre if producto.categoria else '',
            'es_bebida': es_categoria_bebida(producto.categoria.nombre if producto.categoria else ''),
            'control_stock_venta': bool(producto.control_stock_venta),
        }
        for producto in productos
    ]


def crear_combo(cliente_id: int, data: dict) -> dict:
    nombre = str(data.get('nombre') or '').strip()
    if not nombre:
        raise ValueError('Ponele un nombre al combo.')
    precio = parse_price(data.get('precio'))
    if precio <= 0:
        raise ValueError('Falta el precio del combo.')
    incluidos = _productos_cliente(cliente_id, data.get('producto_ids'), MAX_PRODUCTOS_COMBO)
    bebidas = _productos_cliente(cliente_id, data.get('bebida_ids'), MAX_BEBIDAS_COMBO)
    if not incluidos:
        raise ValueError('El combo tiene que incluir al menos un producto.')
    if len(incluidos) + (1 if bebidas else 0) < 2:
        raise ValueError('Un combo necesita al menos dos cosas: suma otro producto o una bebida a eleccion.')

    categoria = _categoria_combos(cliente_id)
    combo = guardar_producto(cliente_id, {
        'categoria_id': categoria.id_categoria,
        'nombre': nombre,
        'precio': precio,
        'descripcion': _descripcion(incluidos, bebidas),
    })
    opciones_bebida = _crear_grupo_bebida(cliente_id, combo, bebidas) if bebidas else []
    _copiar_recetas(cliente_id, combo, incluidos, opciones_bebida)
    return {
        'producto': combo.to_dict(),
        'avisos': _avisos_stock(incluidos + bebidas),
    }


def _productos_cliente(cliente_id: int, ids, maximo: int) -> list[GastronomiaProducto]:
    if ids in (None, ''):
        return []
    if not isinstance(ids, list):
        raise ValueError('Los productos del combo no son validos.')
    # Se permite repetir (ej: 2 empanadas): el orden y las repeticiones se respetan.
    ids = [parse_int(value, 0) for value in ids]
    if any(value <= 0 for value in ids) or len(ids) > maximo:
        raise ValueError('Los productos del combo no son validos.')
    encontrados = {
        int(producto.id_producto): producto
        for producto in GastronomiaProducto.query.filter(
            GastronomiaProducto.cliente_id == int(cliente_id),
            GastronomiaProducto.activo.is_(True),
            GastronomiaProducto.id_producto.in_(set(ids)),
        ).all()
    }
    if len(encontrados) != len(set(ids)):
        raise ValueError('Algun producto del combo ya no existe en el menu.')
    return [encontrados[value] for value in ids]


def _categoria_combos(cliente_id: int) -> GastronomiaCategoria:
    categoria = GastronomiaCategoria.query.filter(
        GastronomiaCategoria.cliente_id == int(cliente_id),
        db.func.lower(GastronomiaCategoria.nombre) == CATEGORIA_COMBOS.lower(),
    ).first()
    if categoria is None:
        return guardar_categoria(cliente_id, {'nombre': CATEGORIA_COMBOS, 'orden': 0, 'visible': True})
    if not categoria.activo:
        categoria.activo = True
        categoria.visible = True
        db.session.commit()
    return categoria


def _descripcion(incluidos: list[GastronomiaProducto], bebidas: list[GastronomiaProducto]) -> str:
    partes = [
        f'{cantidad} x {nombre}' if cantidad > 1 else nombre
        for nombre, cantidad in Counter(producto.nombre for producto in incluidos).items()
    ]
    if bebidas:
        partes.append('bebida a eleccion')
    return 'Incluye: ' + ', '.join(partes) + '.'


def _crear_grupo_bebida(cliente_id: int, combo: GastronomiaProducto, bebidas: list[GastronomiaProducto]):
    grupo = guardar_grupo(cliente_id, combo.id_producto, {
        'nombre': GRUPO_BEBIDA,
        'tipo': 'combo',
        'obligatorio': True,
        'min_selecciones': 1,
        'max_selecciones': 1,
    })
    opciones = []
    for orden, bebida in enumerate(dict.fromkeys(bebidas)):
        opcion = guardar_opcion(cliente_id, grupo.id_grupo, {'nombre': bebida.nombre, 'precio_delta': 0, 'orden': orden})
        opciones.append((opcion, bebida))
    return opciones


def _copiar_recetas(cliente_id: int, combo, incluidos, opciones_bebida) -> None:
    items = Counter()
    for producto in incluidos:
        items.update(_receta(cliente_id, producto.id_producto))
    opciones = [
        {'opcion_id': opcion.id_opcion, 'insumo_id': insumo_id, 'cantidad_delta': cantidad}
        for opcion, bebida in opciones_bebida
        for insumo_id, cantidad in _receta(cliente_id, bebida.id_producto).items()
    ]
    if not items and not opciones:
        return
    guardar_receta(cliente_id, combo.id_producto, {
        'items': [{'insumo_id': insumo_id, 'cantidad': cantidad} for insumo_id, cantidad in items.items()],
        'opciones': opciones,
    })


def _receta(cliente_id: int, producto_id: int) -> Counter:
    return Counter({
        int(item.insumo_id): int(item.cantidad or 0)
        for item in GastronomiaRecetaInsumo.query.filter_by(
            cliente_id=int(cliente_id),
            producto_id=int(producto_id),
            activo=True,
        ).all()
    })


def _avisos_stock(productos: list[GastronomiaProducto]) -> list[str]:
    nombres = sorted({producto.nombre for producto in productos if producto.control_stock_venta})
    if not nombres:
        return []
    return [
        'Estos productos se agotan por unidades y el combo no les descuenta unidades: '
        + ', '.join(nombres) + '.'
    ]
