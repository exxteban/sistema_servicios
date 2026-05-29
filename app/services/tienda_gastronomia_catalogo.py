"""Adaptador del menu gastronomico para la API publica de tienda."""

from math import ceil
from urllib.parse import quote

from app import db
from app.models.tienda import TiendaConfig
from app.utils.tienda_urls import build_category_public_path, build_product_public_path, slugify_tienda_text
from gastronomia.models import GastronomiaCategoria, GastronomiaProducto
from app.services.tienda_presupuesto import mensaje_whatsapp_producto


def categorias_gastronomia_publicas(config: TiendaConfig) -> list[dict]:
    categorias = (
        GastronomiaCategoria.query
        .join(GastronomiaProducto, GastronomiaProducto.categoria_id == GastronomiaCategoria.id_categoria)
        .filter(
            GastronomiaCategoria.cliente_id == int(config.id_cliente),
            GastronomiaCategoria.activo.is_(True),
            GastronomiaCategoria.visible.is_(True),
            GastronomiaProducto.cliente_id == int(config.id_cliente),
            GastronomiaProducto.activo.is_(True),
            GastronomiaProducto.visible.is_(True),
            GastronomiaProducto.disponible.is_(True),
        )
        .distinct()
        .order_by(GastronomiaCategoria.orden.asc(), GastronomiaCategoria.nombre.asc())
        .all()
    )
    return [
        {
            'id': categoria.id_categoria,
            'nombre': categoria.nombre,
            'slug': slugify_tienda_text(categoria.nombre, fallback=str(categoria.id_categoria)),
            'url': build_category_public_path(config.slug, categoria.nombre),
        }
        for categoria in categorias
    ]


def productos_gastronomia_payload(
    config: TiendaConfig,
    q: str = '',
    cat_id: int | None = None,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    query = _query_productos_publicos(config)
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                GastronomiaProducto.nombre.ilike(like),
                GastronomiaProducto.descripcion.ilike(like),
            )
        )
    if cat_id:
        query = query.filter(GastronomiaProducto.categoria_id == int(cat_id))

    total = query.count()
    page = max(1, int(page or 1))
    per_page = max(1, int(per_page or 20))
    productos = (
        query
        .order_by(GastronomiaProducto.orden.asc(), GastronomiaProducto.nombre.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    cards = [_serializar_producto_card(producto, config) for producto in productos]

    return {
        'total': total,
        'page': page,
        'pages': int(ceil(total / per_page)) if total else 0,
        'productos': cards,
        'destacados': [],
        'ofertas': [],
        'recomendados': [],
        'imperdibles': [],
    }


def detalle_producto_gastronomia(config: TiendaConfig, producto_id: int) -> dict | None:
    producto = (
        _query_productos_publicos(config)
        .filter(GastronomiaProducto.id_producto == int(producto_id))
        .first()
    )
    if not producto:
        return None

    relacionados = (
        _query_productos_publicos(config)
        .filter(
            GastronomiaProducto.id_producto != producto.id_producto,
            GastronomiaProducto.categoria_id == producto.categoria_id,
        )
        .order_by(GastronomiaProducto.orden.asc(), GastronomiaProducto.nombre.asc())
        .limit(6)
        .all()
    )
    if len(relacionados) < 6:
        ids = [item.id_producto for item in relacionados] + [producto.id_producto]
        faltantes = (
            _query_productos_publicos(config)
            .filter(GastronomiaProducto.id_producto.notin_(ids))
            .order_by(GastronomiaProducto.orden.asc(), GastronomiaProducto.nombre.asc())
            .limit(6 - len(relacionados))
            .all()
        )
        relacionados.extend(faltantes)

    return {
        **_serializar_producto(producto, config),
        'relacionados': [_serializar_producto_card(item, config) for item in relacionados],
    }


def _query_productos_publicos(config: TiendaConfig):
    return (
        GastronomiaProducto.query
        .join(GastronomiaCategoria, GastronomiaCategoria.id_categoria == GastronomiaProducto.categoria_id)
        .filter(
            GastronomiaProducto.cliente_id == int(config.id_cliente),
            GastronomiaProducto.activo.is_(True),
            GastronomiaProducto.visible.is_(True),
            GastronomiaProducto.disponible.is_(True),
            GastronomiaCategoria.activo.is_(True),
            GastronomiaCategoria.visible.is_(True),
        )
    )


def _serializar_producto(producto: GastronomiaProducto, config: TiendaConfig) -> dict:
    data = _serializar_producto_card(producto, config)
    data['descripcion'] = producto.descripcion or ''
    data['imagenes'] = _imagenes_producto(producto)
    return data


def _serializar_producto_card(producto: GastronomiaProducto, config: TiendaConfig) -> dict:
    return {
        'id': producto.id_producto,
        'slug_producto': slugify_tienda_text(producto.nombre, fallback=str(producto.id_producto)),
        'url_detalle': build_product_public_path(config.slug, producto.id_producto, producto.nombre),
        'nombre': producto.nombre,
        'precio': float(producto.precio or 0),
        'precio_anterior': None,
        'ahorro': None,
        'descuento_porcentaje': None,
        'categoria': producto.categoria.nombre if producto.categoria else None,
        'marca': None,
        'modelo': None,
        'es_servicio': False,
        'disponible': bool(producto.disponible),
        'imagenes': _imagenes_producto(producto)[:1],
        'whatsapp_link': _build_whatsapp_link(producto, config),
        'vistas': 0,
        'es_destacado': False,
        'es_oferta': False,
        'promocion_activa': None,
        'tipo_catalogo': 'gastronomia',
    }


def _imagenes_producto(producto: GastronomiaProducto) -> list[dict]:
    if not producto.imagen_url:
        return []
    return [{
        'id_imagen': None,
        'url': producto.imagen_url,
        'card_url': producto.imagen_url,
        'thumbnail_url': producto.imagen_url,
        'orden': 0,
        'width': None,
        'height': None,
    }]


def _build_whatsapp_link(producto: GastronomiaProducto, config: TiendaConfig) -> str | None:
    if not config.telefono_whatsapp:
        return None
    numero = ''.join(c for c in config.telefono_whatsapp if c.isdigit())
    mensaje = mensaje_whatsapp_producto(config.mensaje_whatsapp_producto, producto, config)
    return f'https://wa.me/{numero}?text={quote(mensaje)}'
