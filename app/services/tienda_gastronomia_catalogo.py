"""Adaptador del menu gastronomico para la API publica de tienda."""

from math import ceil
from urllib.parse import quote

from app import db
from app.models.tienda import TiendaConfig
from app.services.tienda_promociones import (
    active_promotions_query,
    attach_gastronomia_promotion_to_product_data,
    get_active_gastronomia_product_promotion,
    get_active_gastronomia_product_promotion_map,
)
from app.services.tienda_context import resolver_cliente_gastronomia_tienda
from app.utils.tienda_urls import build_category_public_path, build_product_public_path, normalize_store_media_url, slugify_tienda_text
from gastronomia.models import GastronomiaCategoria, GastronomiaGrupoOpciones, GastronomiaOpcionProducto, GastronomiaProducto
from app.services.tienda_presupuesto import mensaje_whatsapp_producto


def categorias_gastronomia_publicas(config: TiendaConfig) -> list[dict]:
    cliente_id = resolver_cliente_gastronomia_tienda(config)
    if not cliente_id:
        return []
    categorias = (
        GastronomiaCategoria.query
        .join(GastronomiaProducto, GastronomiaProducto.categoria_id == GastronomiaCategoria.id_categoria)
        .filter(
            GastronomiaCategoria.cliente_id == int(cliente_id),
            GastronomiaCategoria.activo.is_(True),
            GastronomiaCategoria.visible.is_(True),
            GastronomiaProducto.cliente_id == int(cliente_id),
            GastronomiaProducto.activo.is_(True),
            GastronomiaProducto.visible.is_(True),
            GastronomiaProducto.publicado_tienda.is_(True),
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
    cliente_id = resolver_cliente_gastronomia_tienda(config)
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
    promotions = get_active_gastronomia_product_promotion_map(
        cliente_id,
        [producto.id_producto for producto in productos],
    )
    cards = [
        _serializar_producto_card(producto, config, promotions.get(int(producto.id_producto)))
        for producto in productos
    ]
    ofertas = []
    if cliente_id and page == 1 and not q and not cat_id:
        promotion_product_ids = {
            rel.id_producto
            for promotion in active_promotions_query(cliente_id).all()
            for rel in promotion.gastronomia_productos_rel
        }
        if promotion_product_ids:
            productos_oferta = (
                _query_productos_publicos(config)
                .filter(GastronomiaProducto.id_producto.in_(promotion_product_ids))
                .order_by(GastronomiaProducto.orden.asc(), GastronomiaProducto.nombre.asc())
                .limit(8)
                .all()
            )
            promociones_oferta = get_active_gastronomia_product_promotion_map(
                cliente_id,
                [producto.id_producto for producto in productos_oferta],
            )
            ofertas = [
                _serializar_producto_card(producto, config, promociones_oferta.get(int(producto.id_producto)))
                for producto in productos_oferta
            ]

    return {
        'total': total,
        'page': page,
        'pages': int(ceil(total / per_page)) if total else 0,
        'productos': cards,
        'destacados': [],
        'ofertas': ofertas,
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

    related_promotions = get_active_gastronomia_product_promotion_map(
        producto.cliente_id,
        [item.id_producto for item in relacionados],
    )
    return {
        **_serializar_producto(producto, config),
        'relacionados': [
            _serializar_producto_card(item, config, related_promotions.get(int(item.id_producto)))
            for item in relacionados
        ],
    }


def _query_productos_publicos(config: TiendaConfig):
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


def _serializar_producto(producto: GastronomiaProducto, config: TiendaConfig) -> dict:
    promotion = get_active_gastronomia_product_promotion(producto.cliente_id, producto.id_producto)
    data = _serializar_producto_card(producto, config, promotion)
    data['descripcion'] = producto.descripcion or ''
    data['imagenes'] = _imagenes_producto(producto)
    data['grupos_opciones'] = _grupos_opciones_producto(producto)
    return data


def _serializar_producto_card(producto: GastronomiaProducto, config: TiendaConfig, promotion=None) -> dict:
    data = {
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
        'publicado_tienda': bool(producto.publicado_tienda),
        'imagenes': _imagenes_producto(producto)[:1],
        'tiene_opciones': _producto_tiene_opciones(producto),
        'whatsapp_link': _build_whatsapp_link(producto, config),
        'vistas': 0,
        'es_destacado': False,
        'es_oferta': False,
        'promocion_activa': None,
        'tipo_catalogo': 'gastronomia',
    }
    return attach_gastronomia_promotion_to_product_data(producto, data, promotion)


def _imagenes_producto(producto: GastronomiaProducto) -> list[dict]:
    if not producto.imagen_url:
        return []
    image_url = normalize_store_media_url(producto.imagen_url)
    return [{
        'id_imagen': None,
        'url': image_url,
        'card_url': image_url,
        'thumbnail_url': image_url,
        'orden': 0,
        'width': None,
        'height': None,
    }]


def _producto_tiene_opciones(producto: GastronomiaProducto) -> bool:
    return db.session.query(GastronomiaGrupoOpciones.id_grupo).join(
        GastronomiaOpcionProducto,
        GastronomiaOpcionProducto.grupo_id == GastronomiaGrupoOpciones.id_grupo,
    ).filter(
        GastronomiaGrupoOpciones.cliente_id == producto.cliente_id,
        GastronomiaGrupoOpciones.producto_id == producto.id_producto,
        GastronomiaGrupoOpciones.activo.is_(True),
        GastronomiaGrupoOpciones.visible.is_(True),
        GastronomiaOpcionProducto.activo.is_(True),
        GastronomiaOpcionProducto.visible.is_(True),
        GastronomiaOpcionProducto.disponible.is_(True),
    ).first() is not None


def _grupos_opciones_producto(producto: GastronomiaProducto) -> list[dict]:
    imagenes_menu = _imagenes_publicas_menu_por_nombre(producto.cliente_id)
    grupos = (
        producto.grupos_opciones
        .filter_by(activo=True, visible=True)
        .order_by(GastronomiaGrupoOpciones.orden.asc(), GastronomiaGrupoOpciones.nombre.asc())
    )
    resultado = []
    for grupo in grupos.all():
        opciones = [
            _normalizar_opcion(opcion.to_dict(), imagenes_menu)
            for opcion in grupo.opciones_ordenadas()
            if opcion.visible and opcion.disponible
        ]
        if not opciones:
            continue
        data = grupo.to_dict(incluir_opciones=False)
        data['opciones'] = opciones
        resultado.append(data)
    return resultado


def _normalizar_opcion(opcion: dict, imagenes_menu: dict[str, str] | None = None) -> dict:
    imagen_normalizada = normalize_store_media_url(opcion.get('imagen_url')) if 'imagen_url' in opcion else ''
    if imagen_normalizada:
        opcion['imagen_url'] = imagen_normalizada
        return opcion
    opcion['imagen_url'] = _resolver_imagen_opcion_desde_menu(opcion.get('nombre'), imagenes_menu or {})
    return opcion


def _imagenes_publicas_menu_por_nombre(cliente_id: int) -> dict[str, str]:
    productos = (
        GastronomiaProducto.query
        .filter(
            GastronomiaProducto.cliente_id == int(cliente_id),
            GastronomiaProducto.activo.is_(True),
            GastronomiaProducto.visible.is_(True),
            GastronomiaProducto.publicado_tienda.is_(True),
            GastronomiaProducto.disponible.is_(True),
        )
        .all()
    )
    imagenes = {}
    for item in productos:
        clave = _normalizar_nombre_modificador(item.nombre)
        imagen = normalize_store_media_url(item.imagen_url)
        if clave and imagen and clave not in imagenes:
            imagenes[clave] = imagen
    return imagenes


def _resolver_imagen_opcion_desde_menu(nombre_opcion: str | None, imagenes_menu: dict[str, str]) -> str:
    if not imagenes_menu:
        return ''

    for clave in _claves_busqueda_modificador(nombre_opcion):
        imagen = imagenes_menu.get(clave)
        if imagen:
            return imagen

    for clave in _claves_busqueda_modificador(nombre_opcion):
        coincidencias = {
            imagen
            for nombre_producto, imagen in imagenes_menu.items()
            if nombre_producto.startswith(f'{clave}-') or clave.startswith(f'{nombre_producto}-')
        }
        if len(coincidencias) == 1:
            return coincidencias.pop()
    return ''


def _claves_busqueda_modificador(nombre: str | None) -> list[str]:
    clave = _normalizar_nombre_modificador(nombre)
    if not clave:
        return []

    claves = [clave]
    tokens = [token for token in clave.split('-') if token]
    tokens_filtrados = [token for token in tokens if token not in {
        'sin',
        'extra',
        'extras',
        'adicional',
        'adicionales',
        'agregado',
        'agregados',
        'removible',
        'removibles',
    }]
    if tokens_filtrados:
        claves.append('-'.join(tokens_filtrados))
    if len(tokens) > 1 and tokens[0] == 'sin':
        claves.append('-'.join(tokens[1:]))
    if len(tokens) > 1 and tokens[-1] in {'extra', 'extras', 'adicional', 'adicionales'}:
        claves.append('-'.join(tokens[:-1]))
    return [item for index, item in enumerate(claves) if item and item not in claves[:index]]


def _normalizar_nombre_modificador(nombre: str | None) -> str:
    return slugify_tienda_text(nombre, fallback='')


def _build_whatsapp_link(producto: GastronomiaProducto, config: TiendaConfig) -> str | None:
    if not config.telefono_whatsapp:
        return None
    numero = ''.join(c for c in config.telefono_whatsapp if c.isdigit())
    mensaje = mensaje_whatsapp_producto(config.mensaje_whatsapp_producto, producto, config)
    return f'https://wa.me/{numero}?text={quote(mensaje)}'
