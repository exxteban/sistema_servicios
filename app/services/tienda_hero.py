"""Helpers para la portada hero de la tienda online."""

from __future__ import annotations

from app import db
from app.models.producto import Producto
from app.models.tienda import ProductoImagen, TiendaConfig
from app.services.tienda_context import resolver_cliente_gastronomia_tienda
from app.services.tienda_promociones import (
    attach_gastronomia_promotion_to_product_data,
    attach_promotion_to_product_data,
    get_active_gastronomia_product_promotion_map,
    get_active_product_promotion_map,
)
from app.services.tienda_scope import public_product_query
from app.utils.tienda_urls import build_product_public_path, normalize_store_media_url, slugify_tienda_text
from gastronomia.models import GastronomiaCategoria, GastronomiaProducto


HERO_VISUAL_IMAGE = 'imagen'
HERO_VISUAL_CAROUSEL = 'carrusel'
HERO_CAROUSEL_SPEED_DEFAULT = 5
HERO_CAROUSEL_SPEED_MIN = 2
HERO_CAROUSEL_SPEED_MAX = 15
HERO_CAROUSEL_PRODUCTS_MAX = 12
HERO_CAROUSEL_ANIMATION_FADE = 'fade'
HERO_CAROUSEL_ANIMATION_SLIDE = 'slide'
HERO_CAROUSEL_ANIMATION_ZOOM = 'zoom'
HERO_CAROUSEL_ANIMATION_DEFAULT = HERO_CAROUSEL_ANIMATION_FADE


def normalize_hero_visual_type(value: str | None) -> str:
    normalized = str(value or '').strip().lower()
    if normalized == HERO_VISUAL_CAROUSEL:
        return HERO_VISUAL_CAROUSEL
    return HERO_VISUAL_IMAGE


def normalize_hero_carousel_speed(value, default: int = HERO_CAROUSEL_SPEED_DEFAULT) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(HERO_CAROUSEL_SPEED_MIN, min(HERO_CAROUSEL_SPEED_MAX, parsed))


def normalize_hero_carousel_animation(value: str | None) -> str:
    normalized = str(value or '').strip().lower()
    if normalized in {
        HERO_CAROUSEL_ANIMATION_FADE,
        HERO_CAROUSEL_ANIMATION_SLIDE,
        HERO_CAROUSEL_ANIMATION_ZOOM,
    }:
        return normalized
    return HERO_CAROUSEL_ANIMATION_DEFAULT


def parse_hero_product_ids(value) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = str(value).replace(';', ',').split(',')

    ids = []
    seen = set()
    for raw_item in raw_items:
        try:
            product_id = int(str(raw_item).strip())
        except (TypeError, ValueError):
            continue
        if product_id <= 0 or product_id in seen:
            continue
        ids.append(product_id)
        seen.add(product_id)
        if len(ids) >= HERO_CAROUSEL_PRODUCTS_MAX:
            break
    return ids


def serialize_hero_product_ids(value) -> str | None:
    product_ids = parse_hero_product_ids(value)
    if not product_ids:
        return None
    return ','.join(str(product_id) for product_id in product_ids)


def build_hero_carousel_admin_options(config: TiendaConfig | None, client_scope: int | None, es_gastronomia_tienda: bool) -> list[dict]:
    if es_gastronomia_tienda:
        gastronomia_scope = resolver_cliente_gastronomia_tienda(config) or client_scope
        return _build_gastronomia_admin_options(gastronomia_scope)
    return _build_store_admin_options(client_scope)


def build_hero_carousel_items(config: TiendaConfig) -> list[dict]:
    product_ids = parse_hero_product_ids(getattr(config, 'hero_carrusel_producto_ids', None))
    if not product_ids:
        return []
    if _is_gastronomia_store(config):
        return _build_gastronomia_hero_items(config, product_ids)
    return _build_store_hero_items(config, product_ids)


def _build_store_admin_options(client_scope: int | None) -> list[dict]:
    query = Producto.query.filter(
        Producto.activo.is_(True),
        Producto.publicado_tienda.is_(True),
    )
    if client_scope:
        query = query.filter((Producto.id_cliente == client_scope) | (Producto.id_cliente.is_(None)))
    productos = (
        query
        .order_by(Producto.orden_tienda.asc(), Producto.nombre.asc())
        .limit(200)
        .all()
    )
    return [
        {
            'id': int(producto.id_producto),
            'label': _build_product_option_label(producto.nombre, producto.codigo),
        }
        for producto in productos
    ]


def _build_gastronomia_admin_options(client_scope: int | None) -> list[dict]:
    if not client_scope:
        return []
    productos = (
        GastronomiaProducto.query
        .join(GastronomiaCategoria, GastronomiaCategoria.id_categoria == GastronomiaProducto.categoria_id)
        .filter(
            GastronomiaProducto.cliente_id == int(client_scope),
            GastronomiaProducto.activo.is_(True),
            GastronomiaProducto.visible.is_(True),
            GastronomiaProducto.publicado_tienda.is_(True),
            GastronomiaProducto.disponible.is_(True),
            GastronomiaCategoria.activo.is_(True),
            GastronomiaCategoria.visible.is_(True),
        )
        .order_by(GastronomiaProducto.orden.asc(), GastronomiaProducto.nombre.asc())
        .limit(200)
        .all()
    )
    return [
        {
            'id': int(producto.id_producto),
            'label': _build_product_option_label(producto.nombre, None),
        }
        for producto in productos
    ]


def _build_store_hero_items(config: TiendaConfig, product_ids: list[int]) -> list[dict]:
    productos = public_product_query(config).filter(Producto.id_producto.in_(product_ids)).all()
    if not productos:
        return []

    product_map = {int(producto.id_producto): producto for producto in productos}
    promotion_map = get_active_product_promotion_map(int(config.id_cliente or 0), list(product_map.keys()))
    image_rows = (
        ProductoImagen.query
        .filter(
            ProductoImagen.id_producto.in_(list(product_map.keys())),
            ProductoImagen.activa.isnot(False),
        )
        .order_by(ProductoImagen.id_producto.asc(), ProductoImagen.orden.asc())
        .all()
    )
    image_map = {}
    for image in image_rows:
        image_map.setdefault(int(image.id_producto), image.url)

    items = []
    for product_id in product_ids:
        producto = product_map.get(int(product_id))
        if not producto:
            continue
        image_url = normalize_store_media_url(image_map.get(int(product_id)))
        if not image_url:
            continue
        slide = {
            'id': int(producto.id_producto),
            'nombre': producto.nombre,
            'url_detalle': build_product_public_path(config.slug, producto.id_producto, producto.nombre),
            'hero_image_url': image_url,
            'precio': float(producto.precio_venta or 0),
            'precio_anterior': float(producto.precio_anterior_tienda) if producto.precio_anterior_tienda else None,
            'ahorro': None,
            'descuento_porcentaje': None,
            'promocion_activa': None,
        }
        if slide['precio_anterior'] and slide['precio_anterior'] > slide['precio'] and slide['precio'] > 0:
            slide['ahorro'] = round(slide['precio_anterior'] - slide['precio'], 2)
            if config.mostrar_descuento_porcentaje:
                slide['descuento_porcentaje'] = round(((slide['precio_anterior'] - slide['precio']) / slide['precio_anterior']) * 100)
        items.append(
            attach_promotion_to_product_data(
                producto,
                slide,
                promotion_map.get(int(product_id)),
                allow_discount_percentage=bool(config.mostrar_descuento_porcentaje),
            )
        )
    return items


def _build_gastronomia_hero_items(config: TiendaConfig, product_ids: list[int]) -> list[dict]:
    productos = _query_gastronomia_public_products(config).filter(
        GastronomiaProducto.id_producto.in_(product_ids)
    ).all()
    if not productos:
        return []

    product_map = {int(producto.id_producto): producto for producto in productos}
    gastronomy_client_id = resolver_cliente_gastronomia_tienda(config)
    promotion_map = get_active_gastronomia_product_promotion_map(int(gastronomy_client_id or 0), list(product_map.keys()))
    items = []
    for product_id in product_ids:
        producto = product_map.get(int(product_id))
        if not producto or not producto.imagen_url:
            continue
        slide = {
            'id': int(producto.id_producto),
            'nombre': producto.nombre,
            'url_detalle': build_product_public_path(config.slug, producto.id_producto, producto.nombre),
            'hero_image_url': normalize_store_media_url(producto.imagen_url),
            'precio': float(producto.precio or 0),
            'precio_anterior': None,
            'ahorro': None,
            'descuento_porcentaje': None,
            'promocion_activa': None,
        }
        items.append(attach_gastronomia_promotion_to_product_data(producto, slide, promotion_map.get(int(product_id))))
    return items


def _query_gastronomia_public_products(config: TiendaConfig):
    cliente_id = resolver_cliente_gastronomia_tienda(config)
    if not cliente_id:
        return GastronomiaProducto.query.filter(db.false())
    return (
        GastronomiaProducto.query
        .join(GastronomiaCategoria, GastronomiaCategoria.id_categoria == GastronomiaProducto.categoria_id)
        .filter(
            GastronomiaProducto.cliente_id == int(cliente_id),
            GastronomiaProducto.activo.is_(True),
            GastronomiaProducto.visible.is_(True),
            GastronomiaProducto.publicado_tienda.is_(True),
            GastronomiaProducto.disponible.is_(True),
            GastronomiaCategoria.activo.is_(True),
            GastronomiaCategoria.visible.is_(True),
        )
    )


def _is_gastronomia_store(config: TiendaConfig) -> bool:
    return bool(resolver_cliente_gastronomia_tienda(config))


def _build_product_option_label(nombre: str | None, codigo: str | None) -> str:
    title = (nombre or '').strip() or 'Producto'
    code = (codigo or '').strip()
    if not code:
        return title
    return f'{title} ({code})'
