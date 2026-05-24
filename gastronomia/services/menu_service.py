"""Servicios CRUD para menu gastronomico con alcance por cliente."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError

from app import db
from gastronomia.models import GastronomiaCategoria, GastronomiaProducto


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


def listar_categorias(cliente_id: int, *, incluir_ocultas: bool = True) -> list[GastronomiaCategoria]:
    query = GastronomiaCategoria.query.filter(
        GastronomiaCategoria.cliente_id == int(cliente_id),
        GastronomiaCategoria.activo.is_(True),
    )
    if not incluir_ocultas:
        query = query.filter(GastronomiaCategoria.visible.is_(True))
    return query.order_by(GastronomiaCategoria.orden.asc(), GastronomiaCategoria.nombre.asc()).all()


def listar_productos(cliente_id: int, *, categoria_id: int | None = None, incluir_ocultos: bool = True) -> list[GastronomiaProducto]:
    query = GastronomiaProducto.query.filter(
        GastronomiaProducto.cliente_id == int(cliente_id),
        GastronomiaProducto.activo.is_(True),
    )
    if categoria_id:
        query = query.filter(GastronomiaProducto.categoria_id == int(categoria_id))
    if not incluir_ocultos:
        query = query.filter(GastronomiaProducto.visible.is_(True), GastronomiaProducto.disponible.is_(True))
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
    producto.orden = parse_int(data.get('orden'), 0)
    db.session.add(producto)
    _commit_or_raise_duplicate('Ya existe un producto con ese nombre.')
    return producto


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
