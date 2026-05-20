import json
import os
import re
from html import escape

from flask import Blueprint, current_app, make_response, request, send_from_directory

from app.models.producto import Categoria, Producto
from app.models.tienda import TiendaConfig
from app.services.tienda_scope import find_public_category_by_slug, public_category_query, public_product_query
from app.utils.tienda_urls import build_category_public_path, build_product_public_path

tienda_public_bp = Blueprint('tienda_public', __name__)

PRODUCT_PATH_RE = re.compile(r'^producto/(\d+)(?:-[a-z0-9-]+)?/?$', re.IGNORECASE)
CATEGORY_PATH_RE = re.compile(r'^categoria/([a-z0-9-]+)/?$', re.IGNORECASE)
LOCATION_HINT_RE = re.compile(
    r'(?:\b(?:en|de|desde|a|para|zona|ciudad|cobertura)\b\s+)([a-záéíóúñ0-9][a-záéíóúñ0-9\s\-,]{2,60})',
    re.IGNORECASE,
)


def _dist_dir() -> str:
    return os.path.join(current_app.static_folder, 'tienda_dist')


def _index_path() -> str:
    return os.path.join(_dist_dir(), 'index.html')


def _public_store_query():
    return TiendaConfig.query.filter_by(activa=True)


def _clean_text(value, fallback='') -> str:
    text = re.sub(r'<[^>]+>', '', str(value or '')).strip()
    text = re.sub(r'\s+', ' ', text)
    return text or fallback


def _truncate_text(value: str, limit: int) -> str:
    text = _clean_text(value)
    if not text:
        return ''
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + '…'


def _first_valid_text(*values) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ''


def _extract_seo_location(config: TiendaConfig) -> str:
    direct_text = _first_valid_text(config.texto_cobertura, config.texto_retiro_local)
    if direct_text:
        return _truncate_text(direct_text, 60)

    probe_text = _first_valid_text(
        config.subtitulo_hero_tienda,
        config.texto_portada,
        config.texto_footer_descripcion,
        config.texto_envios,
    )
    if not probe_text:
        return ''
    match = LOCATION_HINT_RE.search(probe_text.lower())
    if not match:
        return ''
    location = _clean_text(match.group(1))
    location = re.split(r'[\.\|\n]|(?:\s+y\s+)', location, maxsplit=1)[0].strip(' ,.-')
    if len(location) < 3:
        return ''
    return _truncate_text(location.title(), 60)


def _extract_store_business(config: TiendaConfig) -> str:
    categories = (
        public_category_query(config)
        .order_by(Categoria.nombre.asc())
        .limit(3)
        .all()
    )
    category_names = [_clean_text(category.nombre) for category in categories if _clean_text(category.nombre)]
    if category_names:
        return ', '.join(category_names[:2])
    fallback_text = _first_valid_text(config.titulo_hero_tienda, config.subtitulo_hero_tienda, config.texto_portada)
    if not fallback_text:
        return 'productos'
    cleaned_fallback = _truncate_text(fallback_text, 80).lower()
    if cleaned_fallback.startswith(('venta de ', 'tienda de ')):
        return cleaned_fallback.replace('venta de ', '', 1).replace('tienda de ', '', 1).strip()
    return cleaned_fallback


def _base_store_path(slug: str) -> str:
    host = (request.host or '').split(':', 1)[0].lower()
    normalized_slug = (slug or '').strip().lower()
    if normalized_slug and host.startswith(f'{normalized_slug}.'):
        return ''
    return f'/tienda/{slug}'


def _absolute_url(value: str | None) -> str:
    raw_value = (value or '').strip()
    if not raw_value:
        return ''
    if re.match(r'^https?://', raw_value, re.IGNORECASE):
        return raw_value
    return request.url_root.rstrip('/') + '/' + raw_value.lstrip('/')


def _store_url(slug: str) -> str:
    return _absolute_url(_base_store_path(slug) or '/')


def _product_url(slug: str, product_id: int, product_name: str | None = None) -> str:
    path = build_product_public_path(slug, product_id, product_name)
    base_path = _base_store_path(slug)
    if base_path:
        return _absolute_url(path)
    relative_path = path.replace(f'/tienda/{slug}/', '/', 1)
    return _absolute_url(relative_path)


def _category_url(slug: str, category_name: str | None = None) -> str:
    path = build_category_public_path(slug, category_name)
    base_path = _base_store_path(slug)
    if base_path:
        return _absolute_url(path)
    relative_path = path.replace(f'/tienda/{slug}/', '/', 1)
    return _absolute_url(relative_path)


def _store_sitemap_url(slug: str) -> str:
    base_path = _base_store_path(slug)
    return _absolute_url(f'{base_path}/sitemap.xml' if base_path else '/sitemap.xml')


def _resolve_primary_image(product: Producto) -> str:
    image = (
        product.imagenes_tienda
        .filter_by(activa=True)
        .first()
    )
    return _absolute_url(getattr(image, 'url', ''))


def _build_store_schema(config: TiendaConfig, canonical_url: str, image_url: str) -> dict:
    location = _extract_seo_location(config)
    social_urls = [
        _clean_text(config.instagram_url),
        _clean_text(config.facebook_url),
        _clean_text(config.youtube_url),
        _clean_text(config.sitio_web),
    ]
    social_urls = [url for url in social_urls if url]
    schema = {
        '@context': 'https://schema.org',
        '@type': 'Store',
        'name': config.nombre_tienda or 'Tienda Online',
        'url': canonical_url,
        'description': _clean_text(
            config.texto_portada or config.subtitulo_hero_tienda or config.texto_footer_descripcion,
            'Catalogo online con atencion por WhatsApp.',
        ),
    }
    if image_url:
        schema['image'] = image_url
    if config.telefono_whatsapp:
        schema['telephone'] = config.telefono_whatsapp
    if config.email_contacto:
        schema['email'] = config.email_contacto
    if location:
        schema['address'] = {
            '@type': 'PostalAddress',
            'addressLocality': location,
            'addressCountry': 'PY',
        }
        schema['areaServed'] = location
    if social_urls:
        schema['sameAs'] = social_urls
    return schema


def _build_category_schema(config: TiendaConfig, category: Categoria, canonical_url: str, image_url: str) -> dict:
    schema = {
        '@context': 'https://schema.org',
        '@type': 'CollectionPage',
        'name': f'{category.nombre} | {config.nombre_tienda or "Tienda Online"}',
        'url': canonical_url,
        'description': _clean_text(
            config.texto_portada or config.subtitulo_hero_tienda or config.texto_footer_descripcion,
            f'Catálogo online de {category.nombre}.',
        ),
        'isPartOf': {
            '@type': 'Store',
            'name': config.nombre_tienda or 'Tienda Online',
            'url': _store_url(config.slug),
        },
    }
    if image_url:
        schema['image'] = image_url
    return schema


def _build_product_schema(config: TiendaConfig, product: Producto, canonical_url: str, image_url: str) -> dict:
    price_value = float(product.precio_venta or 0)
    schema = {
        '@context': 'https://schema.org',
        '@type': 'Product',
        'name': product.nombre,
        'description': _clean_text(
            product.descripcion_tienda or product.descripcion,
            'Producto disponible para compra por WhatsApp.',
        ),
        'url': canonical_url,
        'sku': product.codigo or str(product.id_producto),
        'brand': {
            '@type': 'Brand',
            'name': product.marca or (config.nombre_tienda or 'Tienda Online'),
        },
        'offers': {
            '@type': 'Offer',
            'priceCurrency': 'PYG',
            'price': int(round(price_value)) if price_value else 0,
            'availability': 'https://schema.org/InStock' if (product.stock_actual or 0) > 0 else 'https://schema.org/OutOfStock',
            'url': canonical_url,
        },
    }
    if image_url:
        schema['image'] = [image_url]
    if product.categoria and product.categoria.nombre:
        schema['category'] = product.categoria.nombre
    if product.modelo:
        schema['model'] = product.modelo
    return schema


def _resolve_product_url(config: TiendaConfig, product: Producto) -> str:
    return _product_url(config.slug, product.id_producto, product.nombre)


def _resolve_meta_context(config: TiendaConfig, asset_path: str) -> dict:
    is_product_page = False
    is_category_page = False
    product = None
    category = None
    location = _extract_seo_location(config)
    business = _extract_store_business(config)
    business_phrase = _truncate_text(_clean_text(business, 'productos'), 40)
    city_phrase = f'en {location}' if location else ''
    canonical_url = _store_url(config.slug)
    title = _truncate_text(
        _clean_text(f'{config.nombre_tienda or "Tienda Online"} | {business_phrase} {city_phrase}'.strip()),
        65,
    )
    description = _truncate_text(_clean_text(
        config.texto_portada or config.subtitulo_hero_tienda or config.texto_footer_descripcion,
        f'Catálogo online de {business_phrase} {city_phrase} con atención por WhatsApp.',
    ), 160)
    image_url = _absolute_url(config.imagen_portada or config.logo_url)
    page_type = 'website'
    robots = 'index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1'
    status_code = 200

    normalized_asset_path = (asset_path or '').strip()
    is_assistant_page = normalized_asset_path in {'asistente', 'robot'}

    if is_assistant_page:
        assistant_path = f'{_base_store_path(config.slug)}/asistente' if _base_store_path(config.slug) else '/asistente'
        canonical_url = _absolute_url(assistant_path)
        title = f'Asistente IA | {config.nombre_tienda or "Tienda Online"}'
        description = _truncate_text(
            _clean_text(
                config.texto_apoyo_whatsapp or config.subtitulo_hero_tienda or config.texto_portada,
                f'Asistente IA para resolver consultas de {business_phrase} {city_phrase} y derivar a WhatsApp.',
            ),
            160,
        )
        page_type = 'website'

    category_match = CATEGORY_PATH_RE.match(normalized_asset_path)
    if category_match:
        category = find_public_category_by_slug(config, category_match.group(1))
        if category:
            is_category_page = True
            canonical_url = _category_url(config.slug, category.nombre)
            title = _truncate_text(
                _clean_text(f'{category.nombre} {city_phrase} | {config.nombre_tienda or "Tienda Online"}'),
                65,
            )
            description = _clean_text(
                config.texto_portada or config.subtitulo_hero_tienda or config.texto_footer_descripcion,
                f'Explora {category.nombre} {city_phrase}.',
            )[:160]
            page_type = 'website'

    match = PRODUCT_PATH_RE.match(normalized_asset_path)
    if match:
        product_id = int(match.group(1))
        product = (
            public_product_query(config)
            .filter_by(id_producto=product_id)
            .first()
        )
        if product:
            is_product_page = True
            canonical_url = _resolve_product_url(config, product)
            title = _truncate_text(
                _clean_text(f'{product.nombre} {city_phrase} | {config.nombre_tienda or "Tienda Online"}'),
                65,
            )
            description = _clean_text(
                product.descripcion_tienda or product.descripcion,
                f'{product.nombre} disponible {city_phrase}. {description}',
            )[:160]
            image_url = _resolve_primary_image(product) or image_url
            page_type = 'product'

    invalid_route = bool(normalized_asset_path) and not is_assistant_page and (
        (category_match and not category)
        or (match and not product)
        or (not category_match and not match)
    )
    is_store_home = normalized_asset_path == ''

    if invalid_route:
        title = f'Página no encontrada | {config.nombre_tienda or "Tienda Online"}'
        description = 'La página solicitada no existe o no está disponible en este catálogo.'
        robots = 'noindex,follow'
        status_code = 404

    preload_image_url = image_url if (is_store_home and not invalid_route and image_url) else ''

    if is_product_page and product:
        schema = _build_product_schema(config, product, canonical_url, image_url)
    elif is_category_page and category:
        schema = _build_category_schema(config, category, canonical_url, image_url)
    else:
        schema = _build_store_schema(config, canonical_url, image_url)

    return {
        'title': title,
        'description': description,
        'image_url': image_url,
        'canonical_url': canonical_url,
        'page_type': page_type,
        'site_name': config.nombre_tienda or 'Tienda Online',
        'robots': robots,
        'status_code': status_code,
        'preload_image_url': preload_image_url,
        'schema': schema,
        'keywords': _clean_text(
            ', '.join(
                [
                    config.nombre_tienda or '',
                    business_phrase,
                    location,
                    category.nombre if category else '',
                    product.nombre if product else '',
                ]
            )
        ),
    }


def _render_meta_tags(meta: dict) -> str:
    safe_title = escape(_clean_text(meta.get('title')), quote=True)
    safe_description = escape(_clean_text(meta.get('description')), quote=True)
    safe_image_url = escape((meta.get('image_url') or '').strip(), quote=True)
    safe_canonical_url = escape((meta.get('canonical_url') or '').strip(), quote=True)
    safe_page_type = escape((meta.get('page_type') or 'website').strip(), quote=True)
    safe_site_name = escape(_clean_text(meta.get('site_name') or 'Tienda Online'), quote=True)
    safe_robots = escape((meta.get('robots') or 'index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1').strip(), quote=True)
    safe_keywords = escape(_clean_text(meta.get('keywords')), quote=True)
    safe_preload_image_url = escape((meta.get('preload_image_url') or '').strip(), quote=True)
    safe_schema = escape(
        json.dumps(meta.get('schema') or {}, ensure_ascii=False, separators=(',', ':')),
        quote=False,
    )

    tags = [
        f'<title>{safe_title}</title>',
        f'<meta name="description" content="{safe_description}">',
        f'<meta name="keywords" content="{safe_keywords}">',
        f'<meta name="robots" content="{safe_robots}">',
        f'<link rel="canonical" href="{safe_canonical_url}">',
        f'<link rel="alternate" hreflang="es" href="{safe_canonical_url}">',
        f'<link rel="alternate" hreflang="x-default" href="{safe_canonical_url}">',
        f'<meta property="og:locale" content="es_PY">',
        f'<meta property="og:type" content="{safe_page_type}">',
        f'<meta property="og:site_name" content="{safe_site_name}">',
        f'<meta property="og:title" content="{safe_title}">',
        f'<meta property="og:description" content="{safe_description}">',
        f'<meta property="og:url" content="{safe_canonical_url}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{safe_title}">',
        f'<meta name="twitter:description" content="{safe_description}">',
        f'<meta name="twitter:url" content="{safe_canonical_url}">',
    ]
    if safe_preload_image_url:
        tags.append(f'<link rel="preload" as="image" href="{safe_preload_image_url}">')
    if safe_image_url:
        tags.append(f'<meta property="og:image" content="{safe_image_url}">')
        tags.append(f'<meta property="og:image:alt" content="{safe_title}">')
        tags.append(f'<meta name="twitter:image" content="{safe_image_url}">')
        tags.append(f'<meta name="twitter:image:alt" content="{safe_title}">')
    tags.append(f'<script type="application/ld+json">{safe_schema}</script>')
    return '\n    '.join(tags)


def _serve_index_with_seo(slug, asset_path=''):
    if not os.path.exists(_index_path()):
        return 'Tienda no compilada', 503

    with open(_index_path(), 'r', encoding='utf-8') as file:
        html = file.read()

    config = _public_store_query().filter_by(slug=slug).first()
    if not config:
        response = make_response(html)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response

    meta_context = _resolve_meta_context(config, asset_path)
    meta_tags = _render_meta_tags(meta_context)
    html = re.sub(r'<title>.*?</title>', '', html, flags=re.IGNORECASE | re.DOTALL)

    if '<!-- SEO_META_TAGS -->' in html:
        html = html.replace('<!-- SEO_META_TAGS -->', meta_tags)
    else:
        html = html.replace('</head>', f'{meta_tags}</head>')

    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.status_code = int(meta_context.get('status_code') or 200)
    return response


def _xml_response(body: str):
    response = make_response(body)
    response.headers['Content-Type'] = 'application/xml; charset=utf-8'
    return response


def _build_url_entry(loc: str, lastmod=None) -> str:
    parts = [f'  <url><loc>{escape(loc)}</loc>']
    if lastmod:
        parts.append(f'<lastmod>{escape(lastmod)}</lastmod>')
    parts.append('</url>')
    return ''.join(parts)


@tienda_public_bp.route('/robots.txt')
def robots_txt():
    sitemap_url = _absolute_url('/sitemap.xml')
    body = f'User-agent: *\nAllow: /\n\nSitemap: {sitemap_url}\n'
    response = make_response(body)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    return response


@tienda_public_bp.route('/sitemap.xml')
def sitemap_index():
    stores = _public_store_query().order_by(TiendaConfig.slug.asc()).all()
    entries = []
    for store in stores:
        last_modified = store.fecha_modificacion or store.fecha_creacion
        entries.append(
            f'  <sitemap><loc>{escape(_store_sitemap_url(store.slug))}</loc>'
            f'{f"<lastmod>{last_modified.date().isoformat()}</lastmod>" if last_modified else ""}'
            '</sitemap>'
        )
    sitemap_entries = '\n'.join(entries)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{sitemap_entries}\n'
        '</sitemapindex>'
    )
    return _xml_response(xml)


@tienda_public_bp.route('/tienda/<slug>/sitemap.xml')
def store_sitemap(slug):
    config = _public_store_query().filter_by(slug=slug).first()
    if not config:
        return _xml_response(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
        ), 404

    products = (
        public_product_query(config)
        .order_by(Producto.fecha_modificacion.desc(), Producto.id_producto.asc())
        .all()
    )
    entries = [
        _build_url_entry(
            _store_url(slug),
            (config.fecha_modificacion or config.fecha_creacion).date().isoformat()
            if (config.fecha_modificacion or config.fecha_creacion)
            else None,
        )
    ]
    for category in public_category_query(config).order_by(Categoria.nombre.asc()).all():
        entries.append(
            _build_url_entry(
                _category_url(slug, category.nombre),
                (config.fecha_modificacion or config.fecha_creacion).date().isoformat()
                if (config.fecha_modificacion or config.fecha_creacion)
                else None,
            )
        )
    for product in products:
        last_modified = product.fecha_modificacion or product.fecha_creacion
        entries.append(
            _build_url_entry(
                _product_url(slug, product.id_producto, product.nombre),
                last_modified.date().isoformat() if last_modified else None,
            )
        )

    url_entries = '\n'.join(entries)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{url_entries}\n'
        '</urlset>'
    )
    return _xml_response(xml)


@tienda_public_bp.route('/tienda/<slug>')
def tienda_spa(slug):
    return _serve_index_with_seo(slug)


@tienda_public_bp.route('/robot/<slug>')
def tienda_robot_spa(slug):
    return _serve_index_with_seo(slug, 'asistente')


@tienda_public_bp.route('/tienda/<slug>/<path:asset_path>')
def tienda_spa_assets(slug, asset_path):
    route_path = (asset_path or '').strip()
    if route_path == 'sitemap.xml':
        return store_sitemap(slug)

    file_path = os.path.join(_dist_dir(), route_path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(_dist_dir(), route_path)
    return _serve_index_with_seo(slug, route_path)
