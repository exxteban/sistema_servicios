"""Servicios CRUD para menu gastronomico con alcance por cliente."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import unicodedata

from sqlalchemy.exc import IntegrityError

from app import db
from gastronomia.models import GastronomiaCategoria, GastronomiaProducto


COMIDA_KEYWORDS = {
    'hamburguesa', 'burger', 'sandwich', 'pizza', 'lomo', 'lomito', 'papa',
    'frita', 'milanesa', 'empanada', 'pasta', 'carne', 'pollo', 'minuta',
    'plato', 'comida', 'postre', 'helado',
}
BEBIDA_KEYWORDS = {
    'bebida', 'gaseosa', 'soda', 'agua', 'cerveza', 'cafe', 'jugo',
    'licuado', 'vino', 'whisky', 'trago', 'coctel', 'cocktail',
}
BEBIDA_PHRASES = {'con gas', 'sin gas'}


def parse_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'si', 'sì', 'sí', 'on'}:
        return True
    if text in {'0', 'false', 'no', 'off', ''}:
        return False
    return default


def parse_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_price(value) -> Decimal:
    raw = str(value if value is not None else '').strip()
    if ',' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    else:
        raw = raw.replace(',', '')
    try:
        price = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('El precio debe ser numerico.') from exc
    if price < 0:
        raise ValueError('El precio no puede ser negativo.')
    return price.quantize(Decimal('0.01'))


def ordenar_categorias(categorias: list[GastronomiaCategoria]) -> list[GastronomiaCategoria]:
    return sorted(categorias, key=_categoria_sort_key)


def listar_categorias(cliente_id: int, *, incluir_ocultas: bool = True) -> list[GastronomiaCategoria]:
    query = GastronomiaCategoria.query.filter(
        GastronomiaCategoria.cliente_id == int(cliente_id),
        GastronomiaCategoria.activo.is_(True),
    )
    if not incluir_ocultas:
        query = query.filter(GastronomiaCategoria.visible.is_(True))
    return ordenar_categorias(query.all())


def listar_productos(
    cliente_id: int,
    *,
    categoria_id: int | None = None,
    incluir_ocultos: bool = True,
    incluir_agotados: bool = True,
) -> list[GastronomiaProducto]:
    query = GastronomiaProducto.query.filter(
        GastronomiaProducto.cliente_id == int(cliente_id),
        GastronomiaProducto.activo.is_(True),
    )
    if categoria_id:
        query = query.filter(GastronomiaProducto.categoria_id == int(categoria_id))
    if not incluir_ocultos:
        query = query.filter(GastronomiaProducto.visible.is_(True))
    if not incluir_agotados:
        query = query.filter(GastronomiaProducto.disponible.is_(True))
    return query.order_by(GastronomiaProducto.orden.asc(), GastronomiaProducto.nombre.asc()).all()


def obtener_categoria(cliente_id: int, categoria_id: int) -> GastronomiaCategoria | None:
    return GastronomiaCategoria.query.filter(
        GastronomiaCategoria.cliente_id == int(cliente_id),
        GastronomiaCategoria.id_categoria == int(categoria_id),
        GastronomiaCategoria.activo.is_(True),
    ).first()


def obtener_producto(cliente_id: int, producto_id: int) -> GastronomiaProducto | None:
    return GastronomiaProducto.query.filter(
        GastronomiaProducto.cliente_id == int(cliente_id),
        GastronomiaProducto.id_producto == int(producto_id),
        GastronomiaProducto.activo.is_(True),
    ).first()


def guardar_categoria(cliente_id: int, data: dict, categoria: GastronomiaCategoria | None = None) -> GastronomiaCategoria:
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        raise ValueError('El nombre de la categoria es obligatorio.')
    categoria = categoria or GastronomiaCategoria(cliente_id=int(cliente_id))
    categoria.nombre = nombre[:120]
    categoria.descripcion = (data.get('descripcion') or '').strip() or None
    categoria.orden = parse_int(data.get('orden'), 0)
    categoria.visible = parse_bool(data.get('visible'), True)
    db.session.add(categoria)
    _commit_or_raise_duplicate('Ya existe una categoria con ese nombre.')
    return categoria


def guardar_producto(cliente_id: int, data: dict, producto: GastronomiaProducto | None = None) -> GastronomiaProducto:
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        raise ValueError('El nombre del producto es obligatorio.')
    categoria_id = parse_int(data.get('categoria_id') or data.get('id_categoria'), 0)
    categoria = obtener_categoria(cliente_id, categoria_id)
    if not categoria:
        raise ValueError('La categoria no existe para este cliente.')
    producto = producto or GastronomiaProducto(cliente_id=int(cliente_id))
    producto.categoria_id = categoria.id_categoria
    producto.nombre = nombre[:160]
    producto.descripcion = (data.get('descripcion') or '').strip() or None
    producto.precio = parse_price(data.get('precio'))
    producto.imagen_url = (data.get('imagen_url') or '').strip()[:500] or None
    producto.disponible = parse_bool(data.get('disponible'), True)
    producto.visible = parse_bool(data.get('visible'), True)
    producto.visible_en_tv = parse_bool(
        data.get('visible_en_tv'),
        True if producto.id_producto is None else bool(producto.visible_en_tv),
    )
    producto.publicado_tienda = parse_bool(
        data.get('publicado_tienda'),
        True if producto.id_producto is None else bool(producto.publicado_tienda),
    )
    producto.control_stock_venta = parse_bool(data.get('control_stock_venta'), False)
    producto.stock_disponible = _stock_disponible_desde_payload(data) if producto.control_stock_venta else None
    if producto.control_stock_venta and producto.stock_disponible <= 0:
        producto.disponible = False
    producto.orden = parse_int(data.get('orden'), 0)
    db.session.add(producto)
    _commit_or_raise_duplicate('Ya existe un producto con ese nombre.')
    return producto


def actualizar_estado_producto(cliente_id: int, producto_id: int, data: dict) -> GastronomiaProducto | None:
    producto = obtener_producto(cliente_id, producto_id)
    if not producto:
        return None
    if 'visible' in data:
        producto.visible = parse_bool(data.get('visible'), bool(producto.visible))
    if 'visible_en_tv' in data:
        producto.visible_en_tv = parse_bool(data.get('visible_en_tv'), bool(producto.visible_en_tv))
    if 'publicado_tienda' in data:
        producto.publicado_tienda = parse_bool(data.get('publicado_tienda'), bool(producto.publicado_tienda))
    if 'disponible' in data:
        producto.disponible = parse_bool(data.get('disponible'), bool(producto.disponible))
    if 'control_stock_venta' in data:
        producto.control_stock_venta = parse_bool(data.get('control_stock_venta'), bool(producto.control_stock_venta))
    if 'stock_disponible' in data:
        producto.stock_disponible = _stock_disponible_desde_payload(data)
    if producto.control_stock_venta and producto.stock_disponible is not None and producto.stock_disponible <= 0:
        producto.disponible = False
    db.session.add(producto)
    db.session.commit()
    return producto


def reordenar_categorias(cliente_id: int, categoria_ids: list[int]) -> list[GastronomiaCategoria]:
    ids = [parse_int(value, 0) for value in (categoria_ids or [])]
    if not ids or any(categoria_id <= 0 for categoria_id in ids):
        raise ValueError('El orden recibido no es valido.')
    if len(ids) != len(set(ids)):
        raise ValueError('El orden recibido contiene categorias repetidas.')

    categorias = GastronomiaCategoria.query.filter(
        GastronomiaCategoria.cliente_id == int(cliente_id),
        GastronomiaCategoria.activo.is_(True),
        GastronomiaCategoria.id_categoria.in_(ids),
    ).all()
    categorias_por_id = {int(categoria.id_categoria): categoria for categoria in categorias}
    if len(categorias_por_id) != len(ids):
        raise ValueError('El orden incluye categorias invalidas para este cliente.')

    for index, categoria_id in enumerate(ids, start=1):
        categorias_por_id[categoria_id].orden = index * 10
    db.session.commit()
    return listar_categorias(cliente_id)


def eliminar_categoria(cliente_id: int, categoria_id: int) -> bool:
    categoria = obtener_categoria(cliente_id, categoria_id)
    if not categoria:
        return False
    categoria.activo = False
    for producto in categoria.productos.filter_by(activo=True).all():
        producto.activo = False
    db.session.commit()
    return True


def eliminar_producto(cliente_id: int, producto_id: int) -> bool:
    producto = obtener_producto(cliente_id, producto_id)
    if not producto:
        return False
    producto.activo = False
    db.session.commit()
    return True


def _commit_or_raise_duplicate(message: str) -> None:
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ValueError(message) from exc


def _categoria_sort_key(categoria: GastronomiaCategoria) -> tuple[int, int, str]:
    nombre = _normalizar_nombre_categoria(categoria.nombre)
    return (int(categoria.orden or 0), _categoria_prioridad_default(nombre), nombre)


def _categoria_prioridad_default(nombre: str) -> int:
    if any(keyword in nombre for keyword in COMIDA_KEYWORDS):
        return 0
    if any(phrase in nombre for phrase in BEBIDA_PHRASES) or any(keyword in nombre for keyword in BEBIDA_KEYWORDS):
        return 2
    return 1


def _normalizar_nombre_categoria(nombre: str | None) -> str:
    texto = unicodedata.normalize('NFKD', nombre or '')
    return ''.join(char for char in texto if not unicodedata.combining(char)).lower().strip()


def _stock_disponible_desde_payload(data: dict) -> int:
    return max(0, parse_int(data.get('stock_disponible'), 0))
