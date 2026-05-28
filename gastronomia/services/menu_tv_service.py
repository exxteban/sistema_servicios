"""Servicio para pantalla publica de menu gastronomico en TV."""
from __future__ import annotations

import re
import unicodedata

from app import db
from gastronomia.models import GastronomiaCategoria, GastronomiaClienteConfig, GastronomiaProducto
from gastronomia.services.menu_service import parse_bool, parse_int


DEFAULT_REFRESH_SECONDS = 60
TEMAS_MENU_TV = {'clasico', 'alto_contraste'}


def obtener_o_preparar_config_tv(cliente_id: int) -> GastronomiaClienteConfig | None:
    config = GastronomiaClienteConfig.query.filter_by(cliente_id=int(cliente_id)).first()
    if not config:
        return None
    if not config.menu_tv_slug:
        config.menu_tv_slug = generar_slug_menu_tv(config)
        db.session.commit()
    return config


def actualizar_config_tv(cliente_id: int, data: dict) -> GastronomiaClienteConfig:
    config = obtener_o_preparar_config_tv(cliente_id)
    if not config:
        raise ValueError('Configuracion gastronomica no encontrada.')

    config.menu_tv_publico_activo = parse_bool(data.get('menu_tv_publico_activo'), True)
    config.menu_tv_titulo = _clean_text(data.get('menu_tv_titulo'), 160)
    config.menu_tv_subtitulo = _clean_text(data.get('menu_tv_subtitulo'), 240)
    tema = (data.get('menu_tv_tema') or 'clasico').strip().lower()
    config.menu_tv_tema = tema if tema in TEMAS_MENU_TV else 'clasico'
    config.menu_tv_mostrar_precios = parse_bool(data.get('menu_tv_mostrar_precios'), True)
    config.menu_tv_mostrar_agotados = parse_bool(data.get('menu_tv_mostrar_agotados'), False)
    intervalo = parse_int(data.get('menu_tv_intervalo_refresco_seg'), DEFAULT_REFRESH_SECONDS)
    config.menu_tv_intervalo_refresco_seg = max(15, min(3600, intervalo))
    db.session.commit()
    return config


def obtener_payload_publico(slug: str) -> dict | None:
    config = _config_publica_por_slug(slug)
    if not config:
        return None
    categorias = listar_categorias_menu_tv(config)
    return {
        'ok': True,
        'config': serializar_config_tv(config),
        'categorias': categorias,
    }


def listar_categorias_menu_tv(config: GastronomiaClienteConfig) -> list[dict]:
    categorias = (
        GastronomiaCategoria.query
        .filter_by(cliente_id=int(config.cliente_id), activo=True, visible=True)
        .order_by(GastronomiaCategoria.orden.asc(), GastronomiaCategoria.nombre.asc())
        .all()
    )
    productos = _productos_visibles(config)
    productos_por_categoria: dict[int, list[dict]] = {}
    for producto in productos:
        productos_por_categoria.setdefault(int(producto.categoria_id), []).append(_producto_tv(producto))

    return [
        {
            'id_categoria': categoria.id_categoria,
            'nombre': categoria.nombre,
            'descripcion': categoria.descripcion,
            'orden': int(categoria.orden or 0),
            'productos': productos_por_categoria.get(int(categoria.id_categoria), []),
        }
        for categoria in categorias
        if productos_por_categoria.get(int(categoria.id_categoria))
    ]


def serializar_config_tv(config: GastronomiaClienteConfig) -> dict:
    cliente = getattr(config, 'cliente', None)
    titulo = config.menu_tv_titulo or getattr(cliente, 'nombre', None) or 'Menu'
    return {
        'slug': config.menu_tv_slug,
        'titulo': titulo,
        'subtitulo': config.menu_tv_subtitulo,
        'tema': config.menu_tv_tema or 'clasico',
        'publico_activo': bool(config.menu_tv_publico_activo),
        'mostrar_precios': bool(config.menu_tv_mostrar_precios),
        'mostrar_agotados': bool(config.menu_tv_mostrar_agotados),
        'intervalo_refresco_seg': int(config.menu_tv_intervalo_refresco_seg or DEFAULT_REFRESH_SECONDS),
    }


def generar_slug_menu_tv(config: GastronomiaClienteConfig) -> str:
    cliente = getattr(config, 'cliente', None)
    base = getattr(cliente, 'nombre', None) or f'menu-tv-{config.cliente_id}'
    root = _slugify(base)[:80] or 'menu-tv'
    existentes = {
        item[0]
        for item in db.session.query(GastronomiaClienteConfig.menu_tv_slug)
        .filter(
            GastronomiaClienteConfig.id_config != int(config.id_config or 0),
            GastronomiaClienteConfig.menu_tv_slug.isnot(None),
        )
        .all()
        if item[0]
    }
    slug = root
    counter = 2
    while slug in existentes:
        suffix = f'-{counter}'
        slug = f'{root[:100 - len(suffix)]}{suffix}'
        counter += 1
    return slug


def _config_publica_por_slug(slug: str) -> GastronomiaClienteConfig | None:
    normalized = (slug or '').strip().lower()
    if not normalized or not re.match(r'^[a-z0-9][a-z0-9-]{0,99}$', normalized):
        return None
    return GastronomiaClienteConfig.query.filter(
        GastronomiaClienteConfig.menu_tv_slug == normalized,
        GastronomiaClienteConfig.menu_tv_publico_activo.is_(True),
        GastronomiaClienteConfig.gastronomia_activo.is_(True),
    ).first()


def _productos_visibles(config: GastronomiaClienteConfig) -> list[GastronomiaProducto]:
    query = GastronomiaProducto.query.filter_by(
        cliente_id=int(config.cliente_id),
        activo=True,
        visible=True,
        visible_en_tv=True,
    )
    return query.order_by(GastronomiaProducto.orden.asc(), GastronomiaProducto.nombre.asc()).all()


def _producto_tv(producto: GastronomiaProducto) -> dict:
    return {
        'id_producto': producto.id_producto,
        'nombre': producto.nombre,
        'descripcion': producto.descripcion,
        'precio': float(producto.precio or 0),
        'imagen_url': producto.imagen_url,
        'disponible': bool(producto.disponible),
        'orden': int(producto.orden or 0),
    }


def _clean_text(value, limit: int) -> str | None:
    text = str(value or '').strip()
    return text[:limit] or None


def _slugify(value: str) -> str:
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return re.sub(r'-{2,}', '-', text)
