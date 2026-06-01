"""
API REST pública y privada para la Tienda Online.
Blueprint: tienda_api_bp  –  url_prefix = '/api/tienda'

Endpoints públicos: no requieren autenticación, solo slug válido.
Endpoints admin:    requieren @login_required.

Regla: este archivo solo toca modelos de tienda/ y producto. NUNCA modifica
lógica de ventas, caja, whatsapp u otros módulos del backoffice.
"""
import csv
import hashlib
import os
import re
import unicodedata
from functools import lru_cache
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from threading import Lock
from flask import Blueprint, jsonify, request, current_app, send_from_directory, make_response
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.utils.imagenes import (
    generar_derivado_imagen,
    nombre_derivado_imagen,
    procesar_y_guardar_imagen,
    rotar_imagen_guardada,
)
from PIL import Image, UnidentifiedImageError

from app import db, csrf
from app.models.tienda import TiendaConfig, ProductoImagen, TiendaLead, TiendaVisitaEvento
from app.models.producto import Producto, Categoria
from app.services.tienda_promociones import (
    attach_promotion_to_product_data,
    get_active_product_promotion_map,
    get_active_promotions_for_store,
)
from app.services.tienda_context import buscar_config_tienda_admin, resolver_cliente_tienda, resolver_cliente_tienda_explicito
from app.services.tienda_scope import public_category_query, public_product_query, store_product_scope_filter
from app.services.tienda_estadisticas import obtener_resumen_estadisticas_tienda
from app.services.tienda_gastronomia_catalogo import (
    categorias_gastronomia_publicas,
    detalle_producto_gastronomia,
    productos_gastronomia_payload,
)
from app.services.tienda_presupuesto import config_publica_tienda, mensaje_whatsapp_producto, tienda_es_gastronomia
from app.services.tienda_hero import (
    build_hero_carousel_items,
    normalize_hero_carousel_animation,
    normalize_hero_carousel_speed,
    normalize_hero_visual_type,
    serialize_hero_product_ids,
)
from app.utils.helpers import today_local, parse_iso_date, utc_bounds_for_local_dates
from app.utils.permisos import requiere_permiso
from app.utils.tienda_urls import build_category_public_path, build_product_public_path, normalize_store_media_url, slugify_tienda_text

try:
    from openpyxl import Workbook
    OPENPYXL_DISPONIBLE = True
except ModuleNotFoundError:
    Workbook = None
    OPENPYXL_DISPONIBLE = False

tienda_api_bp = Blueprint('tienda_api', __name__)

# ─────────────────────────────────────────────
# Utilidades internas
# ─────────────────────────────────────────────

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
STOPWORDS_RELACIONADOS = {
    'con', 'sin', 'para', 'por', 'del', 'las', 'los', 'una', 'uno', 'unos', 'unas',
    'de', 'la', 'el', 'en', 'and', 'the'
}
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,79}$')
MAX_SEARCH_QUERY_LENGTH = 120
LEAD_RATE_WINDOW_SECONDS = 600
LEAD_RATE_MAX_REQUESTS = 8
LEAD_HONEYPOT_FIELDS = ('website', 'company', 'address', 'apellido')
_LEAD_RATE_STATE = {}
_LEAD_RATE_LOCK = Lock()


def _ext_permitida(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _config_por_slug(slug: str):
    """Retorna TiendaConfig o None. Centraliza el lookup por slug."""
    normalized_slug = (slug or '').strip().lower()
    if not normalized_slug or not SLUG_RE.match(normalized_slug):
        return None
    return TiendaConfig.query.filter_by(slug=normalized_slug, activa=True).first()


def _normalizar_texto(valor: str | None) -> str:
    texto = unicodedata.normalize('NFKD', str(valor or ''))
    return ''.join(ch for ch in texto if not unicodedata.combining(ch)).lower().strip()


def _coerce_bool(valor, default: bool = False) -> bool:
    if isinstance(valor, bool):
        return valor
    if valor is None:
        return default
    if isinstance(valor, (int, float)):
        return valor != 0
    normalizado = str(valor).strip().lower()
    if normalizado in {'1', 'true', 'on', 'yes', 'si', 'sí'}:
        return True
    if normalizado in {'0', 'false', 'off', 'no'}:
        return False
    return default


def _tokens_relevantes(*valores: str | None) -> set[str]:
    texto = _normalizar_texto(' '.join(str(v or '') for v in valores))
    tokens = re.findall(r'[a-z0-9]+', texto)
    return {
        t for t in tokens
        if len(t) >= 3 and t not in STOPWORDS_RELACIONADOS
    }


def _puntaje_relacion_producto(base: Producto, candidato: Producto) -> tuple[int, int]:
    base_tokens = _tokens_relevantes(base.nombre, base.marca, base.modelo, base.descripcion_tienda, base.descripcion)
    cand_tokens = _tokens_relevantes(candidato.nombre, candidato.marca, candidato.modelo, candidato.descripcion_tienda, candidato.descripcion)
    base_name_tokens = _tokens_relevantes(base.nombre)
    cand_name_tokens = _tokens_relevantes(candidato.nombre)

    tokens_compartidos = base_tokens & cand_tokens
    tokens_nombre_compartidos = base_name_tokens & cand_name_tokens
    score = 0

    if base.id_categoria and candidato.id_categoria and base.id_categoria == candidato.id_categoria:
        score += 35

    marca_base = _normalizar_texto(base.marca)
    marca_candidato = _normalizar_texto(candidato.marca)
    if marca_base and marca_base == marca_candidato:
        score += 20

    modelo_base = _normalizar_texto(base.modelo)
    modelo_candidato = _normalizar_texto(candidato.modelo)
    if modelo_base and modelo_base == modelo_candidato:
        score += 16

    score += min(32, len(tokens_compartidos) * 8)
    score += min(18, len(tokens_nombre_compartidos) * 6)

    if not tokens_compartidos:
        score -= 24

    precio_base = float(base.precio_venta or 0)
    precio_cand = float(candidato.precio_venta or 0)
    if precio_base > 0 and precio_cand > 0:
        variacion = abs(precio_cand - precio_base) / precio_base
        if variacion <= 0.15:
            score += 8
        elif variacion <= 0.40:
            score += 4
        elif variacion >= 2.0:
            score -= 6

    if (candidato.stock_actual or 0) > 0:
        score += 2

    score += min(10, int((candidato.vistas_tienda or 0) / 20))
    return score, len(tokens_compartidos)


def _obtener_relacionados_inteligentes(p: Producto, config: TiendaConfig, limit: int = 6) -> list[Producto]:
    tokens_base = list(_tokens_relevantes(p.nombre, p.marca, p.modelo))[:4]
    filtros_or = []

    if p.id_categoria:
        filtros_or.append(Producto.id_categoria == p.id_categoria)
    if p.marca:
        filtros_or.append(Producto.marca.ilike(p.marca))
    if p.modelo:
        filtros_or.append(Producto.modelo.ilike(p.modelo))
    for token in tokens_base:
        filtros_or.append(Producto.nombre.ilike(f'%{token}%'))

    query = public_product_query(config).filter(
        Producto.id_producto != p.id_producto,
    )
    if filtros_or:
        query = query.filter(db.or_(*filtros_or))

    candidatos = query.order_by(Producto.vistas_tienda.desc(), Producto.nombre.asc()).limit(120).all()
    rankeados = []
    for candidato in candidatos:
        score, shared_tokens = _puntaje_relacion_producto(p, candidato)
        if score > 0:
            rankeados.append((score, shared_tokens, candidato.vistas_tienda or 0, candidato.nombre or '', candidato))

    rankeados.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
    relacionados = [item[4] for item in rankeados[:limit]]

    if len(relacionados) >= limit:
        return relacionados

    ids_existentes = {r.id_producto for r in relacionados}
    faltantes = limit - len(relacionados)
    fallback = (
        public_product_query(config)
        .filter(
            Producto.id_producto != p.id_producto,
            Producto.id_producto.notin_(ids_existentes) if ids_existentes else db.true(),
        )
        .order_by(Producto.vistas_tienda.desc(), Producto.nombre.asc())
        .limit(faltantes)
        .all()
    )
    return relacionados + fallback


def _resolver_id_cliente_actual(data: dict | None = None, *, exigir_explicito: bool = False) -> int | None:
    if exigir_explicito:
        return resolver_cliente_tienda_explicito(data)
    return resolver_cliente_tienda(data)


def _obtener_ip_cliente() -> str | None:
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    ip = (ip or '').strip()
    return ip[:64] if ip else None


def _build_visitante_hash(id_cliente: int, id_producto: int, ip: str | None, user_agent: str | None) -> str:
    base = f'{id_cliente}|{id_producto}|{ip or "-"}|{(user_agent or "").strip().lower()}'
    return hashlib.sha256(base.encode('utf-8')).hexdigest()


def _lead_rate_key(slug: str) -> str:
    ip = _obtener_ip_cliente() or '-'
    user_agent = (request.headers.get('User-Agent', '') or '').strip().lower()[:120]
    return f'{slug}|{ip}|{user_agent}'


def _is_lead_rate_limited(slug: str) -> tuple[bool, int]:
    now_ts = int(datetime.utcnow().timestamp())
    min_ts = now_ts - LEAD_RATE_WINDOW_SECONDS
    key = _lead_rate_key(slug)
    with _LEAD_RATE_LOCK:
        if len(_LEAD_RATE_STATE) > 5000:
            for state_key, values in list(_LEAD_RATE_STATE.items()):
                keep = [v for v in values if v > min_ts]
                if keep:
                    _LEAD_RATE_STATE[state_key] = keep
                else:
                    _LEAD_RATE_STATE.pop(state_key, None)
        bucket = [ts for ts in _LEAD_RATE_STATE.get(key, []) if ts > min_ts]
        if len(bucket) >= LEAD_RATE_MAX_REQUESTS:
            retry_after = max(1, LEAD_RATE_WINDOW_SECONDS - (now_ts - min(bucket)))
            _LEAD_RATE_STATE[key] = bucket
            return True, retry_after
        bucket.append(now_ts)
        _LEAD_RATE_STATE[key] = bucket
        return False, 0


def _lead_tiene_honeypot(data: dict) -> bool:
    for field in LEAD_HONEYPOT_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _registrar_visita_producto(producto: Producto, config: TiendaConfig):
    ip = _obtener_ip_cliente()
    user_agent = (request.headers.get('User-Agent', '') or '').strip()[:255] or None
    referer = (request.headers.get('Referer', '') or '').strip()[:500] or None
    usuario_id = getattr(current_user, 'id_usuario', None) if getattr(current_user, 'is_authenticated', False) else None

    evento = TiendaVisitaEvento(
        id_cliente=config.id_cliente,
        id_producto=producto.id_producto,
        id_usuario=usuario_id,
        ip_address=ip,
        user_agent=user_agent,
        visitante_hash=_build_visitante_hash(config.id_cliente, producto.id_producto, ip, user_agent),
        referer_url=referer,
    )
    db.session.add(evento)
    producto.vistas_tienda = (producto.vistas_tienda or 0) + 1
    db.session.commit()


def _resolver_rango_estadisticas(args):
    rango = (args.get('range') or args.get('periodo') or 'week').strip().lower()
    hoy = today_local()

    if rango == 'day':
        fecha = parse_iso_date(args.get('fecha')) or parse_iso_date(args.get('desde')) or hoy
        return 'day', fecha, fecha
    if rango == 'month':
        return 'month', hoy - timedelta(days=29), hoy
    if rango == 'custom':
        desde = parse_iso_date(args.get('desde')) or hoy - timedelta(days=6)
        hasta = parse_iso_date(args.get('hasta')) or hoy
        if desde > hasta:
            desde, hasta = hasta, desde
        return 'custom', desde, hasta
    return 'week', hoy - timedelta(days=6), hoy


def _iterar_fechas(desde, hasta):
    cursor = desde
    while cursor <= hasta:
        yield cursor
        cursor += timedelta(days=1)


def _obtener_estadisticas_producto(id_cliente: int, producto: Producto, desde, hasta, rango: str) -> dict:
    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)
    base_query = TiendaVisitaEvento.query.filter(
        TiendaVisitaEvento.id_cliente == id_cliente,
        TiendaVisitaEvento.id_producto == producto.id_producto,
        TiendaVisitaEvento.fecha_evento >= start_utc,
        TiendaVisitaEvento.fecha_evento < end_utc,
    )

    total_visitas = base_query.count()
    visitantes_unicos = (
        base_query.with_entities(db.func.count(db.distinct(TiendaVisitaEvento.visitante_hash))).scalar() or 0
    )
    leads_generados = (
        TiendaLead.query.filter(
            TiendaLead.id_cliente == id_cliente,
            TiendaLead.id_producto == producto.id_producto,
            TiendaLead.fecha_creacion >= start_utc,
            TiendaLead.fecha_creacion < end_utc,
        ).count()
    )
    conversion_leads = round((leads_generados / total_visitas) * 100, 2) if total_visitas else 0

    rows = (
        db.session.query(
            db.func.date(TiendaVisitaEvento.fecha_evento),
            db.func.count(TiendaVisitaEvento.id_visita),
            db.func.count(db.distinct(TiendaVisitaEvento.visitante_hash)),
        )
        .filter(
            TiendaVisitaEvento.id_cliente == id_cliente,
            TiendaVisitaEvento.id_producto == producto.id_producto,
            TiendaVisitaEvento.fecha_evento >= start_utc,
            TiendaVisitaEvento.fecha_evento < end_utc,
        )
        .group_by(db.func.date(TiendaVisitaEvento.fecha_evento))
        .order_by(db.func.date(TiendaVisitaEvento.fecha_evento))
        .all()
    )

    por_fecha = {
        str(fecha): {
            'total': int(total or 0),
            'unicos': int(unicos or 0),
        }
        for fecha, total, unicos in rows
    }

    serie = []
    labels = []
    visitas = []
    unicos = []

    for fecha in _iterar_fechas(desde, hasta):
        iso = fecha.isoformat()
        fila = por_fecha.get(iso, {'total': 0, 'unicos': 0})
        item = {
            'fecha': iso,
            'label': fecha.strftime('%d/%m'),
            'total': fila['total'],
            'unicos': fila['unicos'],
        }
        serie.append(item)
        labels.append(item['label'])
        visitas.append(item['total'])
        unicos.append(item['unicos'])

    promedio_diario = round(total_visitas / max(1, len(serie)), 2)

    return {
        'producto': {
            'id_producto': producto.id_producto,
            'nombre': producto.nombre,
            'codigo': producto.codigo,
        },
        'range': rango,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'total_visitas': total_visitas,
        'visitantes_unicos': visitantes_unicos,
        'leads_generados': leads_generados,
        'conversion_leads': conversion_leads,
        'promedio_diario': promedio_diario,
        'labels': labels,
        'datasets': {
            'visitas': visitas,
            'unicos': unicos,
        },
        'serie': serie,
    }


def _nombre_archivo_estadisticas(producto: Producto, extension: str) -> str:
    base = secure_filename(producto.nombre or producto.codigo or f'producto_{producto.id_producto}') or f'producto_{producto.id_producto}'
    marca_tiempo = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return f'estadisticas_{base}_{marca_tiempo}.{extension}'


def _exportar_estadisticas_csv(producto: Producto, estadisticas: dict):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Producto', estadisticas['producto']['nombre']])
    writer.writerow(['Código', estadisticas['producto']['codigo'] or ''])
    writer.writerow(['Rango', estadisticas['range']])
    writer.writerow(['Desde', estadisticas['desde']])
    writer.writerow(['Hasta', estadisticas['hasta']])
    writer.writerow(['Total visitas', estadisticas['total_visitas']])
    writer.writerow(['Visitantes únicos', estadisticas['visitantes_unicos']])
    writer.writerow(['Leads generados', estadisticas['leads_generados']])
    writer.writerow(['Conversión leads (%)', estadisticas['conversion_leads']])
    writer.writerow(['Promedio diario', estadisticas['promedio_diario']])
    writer.writerow([])
    writer.writerow(['Fecha', 'Visitas totales', 'Visitantes únicos'])
    for item in estadisticas['serie']:
        writer.writerow([item['fecha'], item['total'], item['unicos']])

    response = make_response(buffer.getvalue().encode('utf-8-sig'))
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="{_nombre_archivo_estadisticas(producto, "csv")}"'
    return response


def _exportar_estadisticas_xlsx(producto: Producto, estadisticas: dict):
    if not OPENPYXL_DISPONIBLE:
        return jsonify({'error': 'xlsx_no_disponible'}), 400

    wb = Workbook()
    ws = wb.active
    ws.title = 'Estadísticas'
    ws.append(['Producto', estadisticas['producto']['nombre']])
    ws.append(['Código', estadisticas['producto']['codigo'] or ''])
    ws.append(['Rango', estadisticas['range']])
    ws.append(['Desde', estadisticas['desde']])
    ws.append(['Hasta', estadisticas['hasta']])
    ws.append(['Total visitas', estadisticas['total_visitas']])
    ws.append(['Visitantes únicos', estadisticas['visitantes_unicos']])
    ws.append(['Leads generados', estadisticas['leads_generados']])
    ws.append(['Conversión leads (%)', estadisticas['conversion_leads']])
    ws.append(['Promedio diario', estadisticas['promedio_diario']])
    ws.append([])
    ws.append(['Fecha', 'Visitas totales', 'Visitantes únicos'])

    for item in estadisticas['serie']:
        ws.append([item['fecha'], item['total'], item['unicos']])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename="{_nombre_archivo_estadisticas(producto, "xlsx")}"'
    return response


def _calcular_metricas_comerciales(p: Producto, config: TiendaConfig) -> dict:
    precio = float(p.precio_venta or 0)
    precio_anterior = float(p.precio_anterior_tienda) if p.precio_anterior_tienda else None
    ahorro = None
    descuento_porcentaje = None

    if precio_anterior and precio_anterior > precio and precio > 0:
        ahorro = round(precio_anterior - precio, 2)
        if config.mostrar_descuento_porcentaje:
            descuento_porcentaje = round(((precio_anterior - precio) / precio_anterior) * 100)

    return {
        'precio': precio,
        'precio_anterior': precio_anterior,
        'ahorro': ahorro,
        'descuento_porcentaje': descuento_porcentaje,
    }


def _render_whatsapp_message(template: str | None, producto: Producto) -> str:
    plantilla = (template or '').strip()
    if not plantilla:
        tipo = 'servicio' if getattr(producto, 'es_servicio', False) else 'producto'
        return f'Hola, vengo de la tienda web y me interesa el {tipo}: {producto.nombre}'

    reemplazos = {
        '{producto}': producto.nombre or '',
        '{nombre_producto}': producto.nombre or '',
        '{precio}': f"₲ {float(producto.precio_venta or 0):,.0f}".replace(',', '.'),
        '{marca}': producto.marca or '',
        '{modelo}': producto.modelo or '',
    }
    mensaje = plantilla
    for token, valor in reemplazos.items():
        mensaje = mensaje.replace(token, valor)
    return mensaje


def _normalizar_url_media_tienda(url: str | None) -> str:
    return normalize_store_media_url(url)


def _resolver_ruta_media_tienda(url: str | None) -> str | None:
    valor = (url or '').split('?', 1)[0].strip()
    if not valor:
        return None

    valor = valor.replace('\\', '/')
    static_folder = os.path.abspath(current_app.static_folder)
    lower_valor = valor.lower()

    if '/static/' in lower_valor:
        idx = lower_valor.index('/static/') + len('/static/')
        relativo = valor[idx:].lstrip('/')
    elif valor.startswith('static/'):
        relativo = valor[len('static/'):]
    elif 'tienda_uploads/' in lower_valor:
        idx = lower_valor.index('tienda_uploads/')
        relativo = valor[idx:]
    else:
        return None

    ruta = os.path.abspath(os.path.join(static_folder, relativo.replace('/', os.sep)))
    try:
        if os.path.commonpath([static_folder, ruta]) != static_folder:
            return None
    except ValueError:
        return None
    return ruta


def _adjuntar_version_url(url: str, version: int | None) -> str:
    if not url or version is None:
        return url
    separador = '&' if '?' in url else '?'
    return f'{url}{separador}v={int(version)}'


def _url_derivado_media_tienda(url_base: str, ruta: str | None, variante: str) -> str | None:
    if not url_base or not ruta:
        return None
    try:
        nombre_derivado = nombre_derivado_imagen(os.path.basename(ruta), variante)
    except ValueError:
        return None

    ruta_derivada = os.path.join(os.path.dirname(ruta), nombre_derivado)
    if not os.path.isfile(ruta_derivada):
        return None

    url_limpia = url_base.split('?', 1)[0]
    if '/' not in url_limpia:
        return None
    base_url = f"{url_limpia.rsplit('/', 1)[0]}/{nombre_derivado}"
    return _adjuntar_version_url(base_url, int(os.path.getmtime(ruta_derivada)))


@lru_cache(maxsize=4096)
def _leer_dimensiones_imagen(ruta: str, version: int) -> tuple[int, int] | None:
    if not ruta or not os.path.isfile(ruta):
        return None
    try:
        with Image.open(ruta) as imagen:
            width, height = imagen.size
            if width <= 0 or height <= 0:
                return None
            return int(width), int(height)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _serializar_imagen_tienda(data: dict) -> dict:
    url_base = _normalizar_url_media_tienda(data.get('url'))
    ruta = _resolver_ruta_media_tienda(data.get('url'))
    version = None
    dimensiones = None
    if ruta and os.path.isfile(ruta):
        version = int(os.path.getmtime(ruta))
        dimensiones = _leer_dimensiones_imagen(ruta, version)
    width = data.get('width')
    height = data.get('height')
    if dimensiones and not (width and height):
        width, height = dimensiones
    card_url = _url_derivado_media_tienda(url_base, ruta, 'card')
    return {
        **data,
        'url': _adjuntar_version_url(url_base, version),
        'card_url': card_url,
        'thumbnail_url': card_url,
        'width': int(width) if str(width or '').isdigit() and int(width) > 0 else None,
        'height': int(height) if str(height or '').isdigit() and int(height) > 0 else None,
    }


def _serializar_producto(p: Producto, config: TiendaConfig, imagenes_precargadas=None, promocion_activa=None) -> dict:
    """Serialización segura de un producto para la API pública."""
    if imagenes_precargadas is not None:
        imagenes = imagenes_precargadas
    else:
        imagenes = [
            img.to_dict()
            for img in p.imagenes_tienda.filter(ProductoImagen.activa.isnot(False)).order_by(ProductoImagen.orden).all()
        ]
    imagenes = [_serializar_imagen_tienda(img) for img in imagenes]
    metricas = _calcular_metricas_comerciales(p, config)
    slug_producto = slugify_tienda_text(p.nombre, fallback=str(p.id_producto))
    data = {
        'id': p.id_producto,
        'slug_producto': slug_producto,
        'url_detalle': build_product_public_path(config.slug, p.id_producto, p.nombre),
        'nombre': p.nombre,
        'descripcion': p.descripcion_tienda or p.descripcion or '',
        'precio': metricas['precio'],
        'precio_anterior': metricas['precio_anterior'],
        'ahorro': metricas['ahorro'],
        'descuento_porcentaje': metricas['descuento_porcentaje'],
        'categoria': p.categoria.nombre if p.categoria else None,
        'marca': p.marca,
        'modelo': p.modelo,
        'es_servicio': bool(getattr(p, 'es_servicio', False)),
        'disponible': bool(getattr(p, 'es_servicio', False)) or p.stock_actual > 0,
        'imagenes': imagenes,
        'whatsapp_link': _build_wa_link(p, config),
        'vistas': p.vistas_tienda or 0,
        'es_destacado': getattr(p, 'es_destacado_tienda', False),
        'es_oferta': getattr(p, 'es_oferta_tienda', False),
        'promocion_activa': None,
    }
    return attach_promotion_to_product_data(
        p,
        data,
        promocion_activa,
        allow_discount_percentage=bool(config.mostrar_descuento_porcentaje),
    )


def _serializar_producto_card(p: Producto, config: TiendaConfig, imagenes_precargadas=None, promocion_activa=None) -> dict:
    """Serialización liviana para cards/listados públicos."""
    imagenes = imagenes_precargadas or []
    primera_imagen = _serializar_imagen_tienda(imagenes[0]) if imagenes else None
    metricas = _calcular_metricas_comerciales(p, config)
    slug_producto = slugify_tienda_text(p.nombre, fallback=str(p.id_producto))
    data = {
        'id': p.id_producto,
        'slug_producto': slug_producto,
        'url_detalle': build_product_public_path(config.slug, p.id_producto, p.nombre),
        'nombre': p.nombre,
        'precio': metricas['precio'],
        'precio_anterior': metricas['precio_anterior'],
        'ahorro': metricas['ahorro'],
        'descuento_porcentaje': metricas['descuento_porcentaje'],
        'categoria': p.categoria.nombre if p.categoria else None,
        'marca': p.marca,
        'modelo': p.modelo,
        'es_servicio': bool(getattr(p, 'es_servicio', False)),
        'disponible': bool(getattr(p, 'es_servicio', False)) or p.stock_actual > 0,
        'imagenes': [primera_imagen] if primera_imagen else [],
        'whatsapp_link': _build_wa_link(p, config),
        'vistas': p.vistas_tienda or 0,
        'es_destacado': getattr(p, 'es_destacado_tienda', False),
        'es_oferta': getattr(p, 'es_oferta_tienda', False),
        'promocion_activa': None,
    }
    return attach_promotion_to_product_data(
        p,
        data,
        promocion_activa,
        allow_discount_percentage=bool(config.mostrar_descuento_porcentaje),
    )


def _build_wa_link(p: Producto, config: TiendaConfig) -> str | None:
    """Genera link de WhatsApp pre-cargado con nombre del producto."""
    if not config.telefono_whatsapp:
        return None
    # Limpia el número: solo dígitos
    numero = ''.join(c for c in config.telefono_whatsapp if c.isdigit())
    mensaje = mensaje_whatsapp_producto(config.mensaje_whatsapp_producto, p, config)
    import urllib.parse
    return f"https://wa.me/{numero}?text={urllib.parse.quote(mensaje)}"


# ─────────────────────────────────────────────
# API PÚBLICA  –  sin autenticación
# ─────────────────────────────────────────────

@tienda_api_bp.route('/<slug>/config', methods=['GET'])
def get_config(slug: str):
    """Retorna la configuración pública de la tienda."""
    config = _config_por_slug(slug)
    if not config:
        return jsonify({'error': 'tienda_no_encontrada'}), 404
    payload = config_publica_tienda(config)
    payload['hero_carrusel_items'] = build_hero_carousel_items(config)
    return jsonify(payload)


@tienda_api_bp.route('/<slug>/categorias', methods=['GET'])
def get_categorias(slug: str):
    """Retorna categorías que tienen al menos un producto publicado."""
    config = _config_por_slug(slug)
    if not config:
        return jsonify({'error': 'tienda_no_encontrada'}), 404

    return jsonify(_categorias_publicas(config))


def _categorias_publicas(config: TiendaConfig) -> list[dict]:
    if tienda_es_gastronomia(config):
        return categorias_gastronomia_publicas(config)

    categorias = public_category_query(config).order_by(Categoria.nombre).all()
    return [
        {
            'id': c.id_categoria,
            'nombre': c.nombre,
            'slug': slugify_tienda_text(c.nombre, fallback=str(c.id_categoria)),
            'url': build_category_public_path(config.slug, c.nombre),
        }
        for c in categorias
    ]


def _build_productos_payload(config: TiendaConfig, q: str = '', cat_id: int | None = None, page: int = 1, per_page: int = 20) -> dict:
    if tienda_es_gastronomia(config):
        return productos_gastronomia_payload(config, q=q, cat_id=cat_id, page=page, per_page=per_page)

    query = public_product_query(config)

    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Producto.nombre.ilike(like),
                Producto.marca.ilike(like),
                Producto.modelo.ilike(like),
            )
        )

    if cat_id:
        query = query.filter(Producto.id_categoria == cat_id)

    query = query.options(db.joinedload(Producto.categoria)).order_by(Producto.orden_tienda.asc(), Producto.nombre.asc())
    paginado = query.paginate(page=page, per_page=per_page, error_out=False)

    destacados_raw = []
    ofertas_raw = []
    recomendados_raw = []
    imperdibles_raw = []
    if page == 1 and not q and not cat_id:
        promo_product_ids = {
            rel.id_producto
            for promotion in get_active_promotions_for_store(config)
            for rel in promotion.productos_rel
        }
        destacados_raw = public_product_query(config).filter(
            Producto.es_destacado_tienda.is_(True)
        ).options(db.joinedload(Producto.categoria)).order_by(Producto.orden_tienda.asc(), Producto.nombre.asc()).limit(8).all()

        ofertas_raw = public_product_query(config).filter(
            db.or_(
                Producto.es_oferta_tienda.is_(True),
                Producto.id_producto.in_(promo_product_ids) if promo_product_ids else db.false(),
            )
        ).options(db.joinedload(Producto.categoria)).order_by(Producto.orden_tienda.asc(), Producto.nombre.asc()).limit(8).all()

        productos_home_raw = query.limit(24).all()
        ids_ya_usados = {p.id_producto for p in destacados_raw + ofertas_raw}
        secundarios_raw = [p for p in productos_home_raw if p.id_producto not in ids_ya_usados]
        recomendados_raw = secundarios_raw[:8]
        imperdibles_raw = secundarios_raw[8:16]

    todos_los_productos = paginado.items + destacados_raw + ofertas_raw + recomendados_raw + imperdibles_raw
    product_ids = {p.id_producto for p in todos_los_productos}

    imagenes_por_producto = {}
    if product_ids:
        imagenes_raw = ProductoImagen.query.filter(
            ProductoImagen.id_producto.in_(product_ids),
            ProductoImagen.activa.isnot(False)
        ).order_by(ProductoImagen.orden).all()
        for img in imagenes_raw:
            if img.id_producto not in imagenes_por_producto:
                imagenes_por_producto[img.id_producto] = [img.to_dict()]

    active_promotions = get_active_product_promotion_map(
        int(config.id_cliente),
        product_ids,
    )

    def card(p: Producto) -> dict:
        return _serializar_producto_card(
            p,
            config,
            imagenes_por_producto.get(p.id_producto, []),
            active_promotions.get(p.id_producto),
        )

    return {
        'total': paginado.total,
        'page': paginado.page,
        'pages': paginado.pages,
        'productos': [card(p) for p in paginado.items],
        'destacados': [card(p) for p in destacados_raw],
        'ofertas': [card(p) for p in ofertas_raw],
        'recomendados': [card(p) for p in recomendados_raw],
        'imperdibles': [card(p) for p in imperdibles_raw],
    }


@tienda_api_bp.route('/<slug>/productos', methods=['GET'])
def get_productos(slug: str):
    """
    Retorna productos publicados.
    Query params: q (búsqueda), categoria (id), page (1-based), per_page (max 40).
    """
    config = _config_por_slug(slug)
    if not config:
        return jsonify({'error': 'tienda_no_encontrada'}), 404

    q = request.args.get('q', '').strip()[:MAX_SEARCH_QUERY_LENGTH]
    cat_id = request.args.get('categoria', type=int)
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(40, max(1, request.args.get('per_page', 20, type=int)))
    return jsonify(_build_productos_payload(config, q=q, cat_id=cat_id, page=page, per_page=per_page))


@tienda_api_bp.route('/<slug>/bootstrap', methods=['GET'])
def get_bootstrap(slug: str):
    """Carga inicial compacta para la home de la tienda."""
    config = _config_por_slug(slug)
    if not config:
        return jsonify({'error': 'tienda_no_encontrada'}), 404

    config_payload = config_publica_tienda(config)
    config_payload['hero_carrusel_items'] = build_hero_carousel_items(config)

    return jsonify({
        'config': config_payload,
        'categorias': _categorias_publicas(config),
        'catalogo': _build_productos_payload(config, page=1, per_page=12),
    })


@tienda_api_bp.route('/<slug>/producto/<int:id_producto>', methods=['GET'])
def get_producto_detalle(slug: str, id_producto: int):
    """Detalle completo de un producto individual."""
    config = _config_por_slug(slug)
    if not config:
        return jsonify({'error': 'tienda_no_encontrada'}), 404

    if tienda_es_gastronomia(config):
        data = detalle_producto_gastronomia(config, id_producto)
        if not data:
            return jsonify({'error': 'producto_no_encontrado'}), 404
        return jsonify(data)

    p = public_product_query(config).filter_by(id_producto=id_producto).first()
    if not p:
        return jsonify({'error': 'producto_no_encontrado'}), 404

    _registrar_visita_producto(p, config)

    relacionados_raw = _obtener_relacionados_inteligentes(p, config, limit=6)
    relacionados_ids = [r.id_producto for r in relacionados_raw]
    promo_ids = relacionados_ids + [p.id_producto]
    active_promotions = get_active_product_promotion_map(
        int(config.id_cliente),
        promo_ids,
    )
    imagenes_por_producto = {}
    if relacionados_ids:
        imagenes_raw = ProductoImagen.query.filter(
            ProductoImagen.id_producto.in_(relacionados_ids),
            ProductoImagen.activa.isnot(False)
        ).order_by(ProductoImagen.orden).all()
        for img in imagenes_raw:
            imagenes_por_producto.setdefault(img.id_producto, []).append(img.to_dict())

    return jsonify({
        **_serializar_producto(p, config, promocion_activa=active_promotions.get(p.id_producto)),
        'relacionados': [
            _serializar_producto_card(r, config, imagenes_por_producto.get(r.id_producto, []), active_promotions.get(r.id_producto))
            for r in relacionados_raw
        ],
    })


@tienda_api_bp.route('/media/<path:rel_path>', methods=['GET'])
def get_media_tienda(rel_path: str):
    base_dir = os.path.join(current_app.static_folder, 'tienda_uploads')
    safe_rel_path = (rel_path or '').replace('\\', '/').lstrip('/')
    if safe_rel_path.lower().startswith('tienda_uploads/'):
        safe_rel_path = safe_rel_path[len('tienda_uploads/'):]
    return send_from_directory(base_dir, safe_rel_path)


@tienda_api_bp.route('/lead', methods=['POST'])
@csrf.exempt
def post_lead():
    data = request.get_json(silent=True) or {}

    slug = data.get('slug', '').strip()
    config = _config_por_slug(slug)
    if not config:
        return jsonify({'error': 'tienda_no_encontrada'}), 404
    if _lead_tiene_honeypot(data):
        return jsonify({'error': 'solicitud_invalida'}), 400
    rate_limited, retry_after = _is_lead_rate_limited(slug)
    if rate_limited:
        response = jsonify({'error': 'demasiadas_solicitudes', 'retry_after': retry_after})
        response.headers['Retry-After'] = str(retry_after)
        response.headers['Cache-Control'] = 'no-store'
        return response, 429

    nombre = (data.get('nombre') or '').strip()
    if not nombre or len(nombre) > 200:
        return jsonify({'error': 'nombre_requerido'}), 400

    telefono = (data.get('telefono') or '').strip()
    email = (data.get('email') or '').strip().lower()
    mensaje = (data.get('mensaje') or '').strip()
    id_producto = data.get('id_producto', None)

    if telefono and len(telefono) > 50:
        return jsonify({'error': 'telefono_invalido'}), 400
    if email and (len(email) > 120 or not EMAIL_RE.match(email)):
        return jsonify({'error': 'email_invalido'}), 400
    if mensaje and len(mensaje) > 2000:
        return jsonify({'error': 'mensaje_invalido'}), 400
    if id_producto not in (None, ''):
        try:
            id_producto = int(id_producto)
        except (TypeError, ValueError):
            return jsonify({'error': 'producto_invalido'}), 400
        producto = public_product_query(config).filter_by(id_producto=id_producto).first()
        if not producto:
            return jsonify({'error': 'producto_invalido'}), 400
    else:
        id_producto = None

    lead = TiendaLead(
        id_cliente=config.id_cliente,
        id_producto=id_producto,
        nombre_contacto=nombre,
        telefono_contacto=telefono or None,
        email_contacto=email or None,
        mensaje=mensaje or None,
    )
    db.session.add(lead)
    db.session.commit()
    return jsonify({'ok': True}), 201


# ─────────────────────────────────────────────
# API PRIVADA  –  requiere login Flask
# ─────────────────────────────────────────────

@tienda_api_bp.route('/admin/producto/<int:id_producto>/toggle', methods=['POST'])
@tienda_api_bp.route('/admin/producto/<int:id_producto>/publicar', methods=['POST'])
@login_required
@requiere_permiso('editar_configuracion')
def admin_toggle_publicar(id_producto: int):
    """Activa o desactiva publicación en tienda de un producto."""
    p = Producto.query.get_or_404(id_producto)
    data = request.get_json(silent=True) or {}
    id_cliente_actual = _resolver_id_cliente_actual(data)

    if 'publicar' in data:
        p.publicado_tienda = _coerce_bool(data.get('publicar'), p.publicado_tienda)
    if 'destacado' in data:
        p.es_destacado_tienda = _coerce_bool(data.get('destacado'), p.es_destacado_tienda)
    if 'oferta' in data:
        p.es_oferta_tienda = _coerce_bool(data.get('oferta'), p.es_oferta_tienda)
        if not p.es_oferta_tienda:
            p.precio_anterior_tienda = None
    if 'precio_anterior' in data:
        try:
            precio_ant = float(data['precio_anterior']) if data['precio_anterior'] else None
            p.precio_anterior_tienda = precio_ant
        except (TypeError, ValueError):
            p.precio_anterior_tienda = None
    
    if 'descripcion_tienda' in data:
        p.descripcion_tienda = data['descripcion_tienda'] or None
    if 'orden_tienda' in data:
        try:
            p.orden_tienda = int(data['orden_tienda'])
        except (TypeError, ValueError):
            pass

    if p.publicado_tienda or p.es_destacado_tienda or p.es_oferta_tienda:
        if not id_cliente_actual:
            return jsonify({'error': 'cliente_no_encontrado'}), 404
        if p.id_cliente and int(p.id_cliente) != int(id_cliente_actual):
            return jsonify({'error': 'producto_asociado_a_otro_cliente'}), 409
        if not p.id_cliente:
            p.id_cliente = id_cliente_actual

    db.session.commit()
    return jsonify({
        'ok': True,
        'publicado_tienda': p.publicado_tienda,
        'es_destacado_tienda': p.es_destacado_tienda,
        'es_oferta_tienda': p.es_oferta_tienda,
    })


@tienda_api_bp.route('/admin/producto/<int:id_producto>/estadisticas', methods=['GET'])
@login_required
@requiere_permiso('ver_reportes')
def admin_producto_estadisticas(id_producto: int):
    producto = Producto.query.get_or_404(id_producto)
    id_cliente = _resolver_id_cliente_actual(request.args, exigir_explicito=True)
    if not id_cliente:
        return jsonify({'error': 'cliente_no_encontrado'}), 404

    rango, desde, hasta = _resolver_rango_estadisticas(request.args)
    estadisticas = _obtener_estadisticas_producto(id_cliente, producto, desde, hasta, rango)
    return jsonify({'ok': True, **estadisticas})


@tienda_api_bp.route('/admin/producto/<int:id_producto>/estadisticas/export', methods=['GET'])
@login_required
@requiere_permiso('ver_reportes')
def admin_producto_estadisticas_export(id_producto: int):
    producto = Producto.query.get_or_404(id_producto)
    id_cliente = _resolver_id_cliente_actual(request.args, exigir_explicito=True)
    if not id_cliente:
        return jsonify({'error': 'cliente_no_encontrado'}), 404

    formato = (request.args.get('format') or 'csv').strip().lower()
    rango, desde, hasta = _resolver_rango_estadisticas(request.args)
    estadisticas = _obtener_estadisticas_producto(id_cliente, producto, desde, hasta, rango)

    if formato == 'xlsx':
        return _exportar_estadisticas_xlsx(producto, estadisticas)
    return _exportar_estadisticas_csv(producto, estadisticas)


@tienda_api_bp.route('/admin/estadisticas/productos-mas-vistos', methods=['GET'])
@login_required
@requiere_permiso('ver_reportes')
def admin_estadisticas_productos_mas_vistos():
    id_cliente = _resolver_id_cliente_actual(request.args, exigir_explicito=True)
    if not id_cliente:
        return jsonify({'error': 'cliente_no_encontrado'}), 404

    rango, desde, hasta = _resolver_rango_estadisticas(request.args)
    categoria_id = request.args.get('categoria_id', type=int)
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(50, max(5, request.args.get('per_page', 10, type=int)))

    data = obtener_resumen_estadisticas_tienda(
        id_cliente=id_cliente,
        desde=desde,
        hasta=hasta,
        categoria_id=categoria_id,
        page=page,
        per_page=per_page,
    )
    return jsonify({
        'ok': True,
        'range': rango,
        'categoria_id': categoria_id,
        **data,
    })


@tienda_api_bp.route('/admin/config', methods=['POST'])
@login_required
@requiere_permiso('editar_configuracion')
def admin_guardar_config():
    """Guarda la configuración de tienda del cliente logueado."""
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()

    id_cliente = resolver_cliente_tienda(data, crear_si_falta=True)
    if not id_cliente:
        return jsonify({'error': 'sin_cliente_asociado'}), 400

    config = buscar_config_tienda_admin(data, id_cliente)
    if config:
        config_cliente = TiendaConfig.query.filter_by(id_cliente=id_cliente).first()
        if config_cliente and config_cliente.id_config != config.id_config:
            config = config_cliente
        else:
            config.id_cliente = int(id_cliente)
    else:
        config = TiendaConfig.query.filter_by(id_cliente=id_cliente).first()
    if not config:
        slug = str(data.get('slug', '')).strip().lower().replace(' ', '-')
        if slug == 'none':
            slug = ''
        if not slug:
            return jsonify({'error': 'slug_requerido'}), 400
        config = TiendaConfig(id_cliente=id_cliente, slug=slug)
        db.session.add(config)

    def parse_bool(key: str, default=False):
        value = data.get(key, default)
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {'1', 'true', 'on', 'yes', 'si', 'sí'}

    def clean_text(key: str):
        if key not in data:
            return None
        value = data.get(key)
        if value is None:
            return None
        clean = str(value).strip()
        if not clean or clean.lower() == 'none':
            return None
        return clean

    def clean_meta_pixel_id(key: str):
        value = clean_text(key)
        if not value:
            return None
        digits = ''.join(ch for ch in value if ch.isdigit())
        return digits[:32] or None

    if 'nombre_tienda' in data:
        config.nombre_tienda = clean_text('nombre_tienda')
    if 'titulo_header_tienda' in data:
        config.titulo_header_tienda = clean_text('titulo_header_tienda')
    if 'logo_url' in data:
        config.logo_url = clean_text('logo_url')
    if 'color_primario' in data:
        config.color_primario = clean_text('color_primario') or '#6366f1'
    if 'telefono_whatsapp' in data:
        config.telefono_whatsapp = clean_text('telefono_whatsapp')
    if 'mensaje_whatsapp' in data:
        config.mensaje_whatsapp = clean_text('mensaje_whatsapp')
    if 'mensaje_whatsapp_general' in data:
        config.mensaje_whatsapp = clean_text('mensaje_whatsapp_general')
    if 'titulo_hero_tienda' in data:
        config.titulo_hero_tienda = clean_text('titulo_hero_tienda')
    if 'subtitulo_hero_tienda' in data:
        config.subtitulo_hero_tienda = clean_text('subtitulo_hero_tienda')
    if 'texto_boton_hero' in data:
        config.texto_boton_hero = clean_text('texto_boton_hero') or 'Explorar catálogo'
    if 'hero_visual_tipo' in data:
        config.hero_visual_tipo = normalize_hero_visual_type(clean_text('hero_visual_tipo'))
    if 'hero_carrusel_producto_ids' in data:
        config.hero_carrusel_producto_ids = serialize_hero_product_ids(data.get('hero_carrusel_producto_ids'))
    if 'hero_carrusel_velocidad_segundos' in data:
        config.hero_carrusel_velocidad_segundos = normalize_hero_carousel_speed(data.get('hero_carrusel_velocidad_segundos'))
    if 'hero_carrusel_animacion' in data:
        config.hero_carrusel_animacion = normalize_hero_carousel_animation(data.get('hero_carrusel_animacion'))
    if 'beneficio_home_1_texto' in data:
        config.beneficio_home_1_texto = clean_text('beneficio_home_1_texto')
    if 'beneficio_home_2_texto' in data:
        config.beneficio_home_2_texto = clean_text('beneficio_home_2_texto')
    if 'beneficio_home_3_texto' in data:
        config.beneficio_home_3_texto = clean_text('beneficio_home_3_texto')
    if 'mensaje_whatsapp_producto' in data:
        config.mensaje_whatsapp_producto = clean_text('mensaje_whatsapp_producto')
    if 'texto_portada' in data:
        config.texto_portada = clean_text('texto_portada')
    if 'titulo_destacados' in data:
        config.titulo_destacados = clean_text('titulo_destacados')
    if 'titulo_ofertas' in data:
        config.titulo_ofertas = clean_text('titulo_ofertas')
    if 'titulo_recomendados' in data:
        config.titulo_recomendados = clean_text('titulo_recomendados')
    if 'titulo_imperdibles' in data:
        config.titulo_imperdibles = clean_text('titulo_imperdibles')
    if 'titulo_footer' in data:
        config.titulo_footer = clean_text('titulo_footer')
    if 'texto_footer_descripcion' in data:
        config.texto_footer_descripcion = clean_text('texto_footer_descripcion')
    if 'texto_politicas_envio' in data:
        config.texto_politicas_envio = clean_text('texto_politicas_envio')
    if 'link_politicas_envio' in data:
        config.link_politicas_envio = clean_text('link_politicas_envio')
    if 'texto_politicas_cambios' in data:
        config.texto_politicas_cambios = clean_text('texto_politicas_cambios')
    if 'link_politicas_cambios' in data:
        config.link_politicas_cambios = clean_text('link_politicas_cambios')
    if 'email_contacto' in data:
        config.email_contacto = clean_text('email_contacto')
    if 'sitio_web' in data:
        config.sitio_web = clean_text('sitio_web')
    if 'instagram_url' in data:
        config.instagram_url = clean_text('instagram_url')
    if 'facebook_url' in data:
        config.facebook_url = clean_text('facebook_url')
    if 'meta_pixel_id' in data:
        config.meta_pixel_id = clean_meta_pixel_id('meta_pixel_id')
    if 'youtube_url' in data:
        config.youtube_url = clean_text('youtube_url')
    if 'texto_cta_catalogo' in data:
        config.texto_cta_catalogo = clean_text('texto_cta_catalogo') or 'Consultar'
    if 'texto_cta_producto' in data:
        config.texto_cta_producto = clean_text('texto_cta_producto') or 'Comprar por WhatsApp'
    if 'texto_whatsapp_confianza' in data:
        config.texto_whatsapp_confianza = clean_text('texto_whatsapp_confianza')
    if 'texto_envios' in data:
        config.texto_envios = clean_text('texto_envios')
    if 'texto_retiro_local' in data:
        config.texto_retiro_local = clean_text('texto_retiro_local')
    if 'texto_garantia' in data:
        config.texto_garantia = clean_text('texto_garantia')
    if 'texto_horarios' in data:
        config.texto_horarios = clean_text('texto_horarios')
    if 'texto_cobertura' in data:
        config.texto_cobertura = clean_text('texto_cobertura')
    if 'texto_apoyo_whatsapp' in data:
        config.texto_apoyo_whatsapp = clean_text('texto_apoyo_whatsapp')
    if 'texto_recordatorio_whatsapp' in data:
        config.texto_recordatorio_whatsapp = clean_text('texto_recordatorio_whatsapp')
    if 'beneficio_producto_1' in data:
        config.beneficio_producto_1 = clean_text('beneficio_producto_1')
    if 'beneficio_producto_2' in data:
        config.beneficio_producto_2 = clean_text('beneficio_producto_2')
    if 'beneficio_producto_3' in data:
        config.beneficio_producto_3 = clean_text('beneficio_producto_3')
    if 'titulo_relacionados' in data:
        config.titulo_relacionados = clean_text('titulo_relacionados') or 'Productos relacionados'
    config.mostrar_hero_tienda = parse_bool('mostrar_hero_tienda', True)
    config.mostrar_titulo_hero_tienda = parse_bool('mostrar_titulo_hero_tienda', True)
    config.mostrar_subtitulo_hero_tienda = parse_bool('mostrar_subtitulo_hero_tienda', True)
    config.mostrar_boton_hero_tienda = parse_bool('mostrar_boton_hero_tienda', True)
    config.mostrar_bloque_beneficios_home = parse_bool('mostrar_bloque_beneficios_home', False)
    config.mostrar_destacados = parse_bool('mostrar_destacados', True)
    config.mostrar_ofertas = parse_bool('mostrar_ofertas', True)
    config.mostrar_seccion_recomendados = parse_bool('mostrar_seccion_recomendados', False)
    config.mostrar_seccion_imperdibles = parse_bool('mostrar_seccion_imperdibles', False)
    config.mostrar_titulo_footer = parse_bool('mostrar_titulo_footer', False)
    config.mostrar_footer_enlaces = parse_bool('mostrar_footer_enlaces', True)
    config.mostrar_politicas_envio = parse_bool('mostrar_politicas_envio', False)
    config.mostrar_politicas_cambios = parse_bool('mostrar_politicas_cambios', False)
    config.mostrar_email_contacto = parse_bool('mostrar_email_contacto', False)
    config.mostrar_sitio_web = parse_bool('mostrar_sitio_web', False)
    config.mostrar_instagram = parse_bool('mostrar_instagram', False)
    config.mostrar_facebook = parse_bool('mostrar_facebook', False)
    config.mostrar_youtube = parse_bool('mostrar_youtube', False)
    config.mostrar_whatsapp_confianza = parse_bool('mostrar_whatsapp_confianza', False)
    config.mostrar_envios = parse_bool('mostrar_envios', False)
    config.mostrar_retiro_local = parse_bool('mostrar_retiro_local', False)
    config.mostrar_garantia = parse_bool('mostrar_garantia', False)
    config.mostrar_horarios = parse_bool('mostrar_horarios', False)
    config.mostrar_cobertura = parse_bool('mostrar_cobertura', False)
    config.mostrar_texto_apoyo_whatsapp = parse_bool('mostrar_texto_apoyo_whatsapp', False)
    config.mostrar_recordatorio_whatsapp = parse_bool('mostrar_recordatorio_whatsapp', False)
    config.mostrar_beneficios_producto = parse_bool('mostrar_beneficios_producto', False)
    config.mostrar_bloque_confianza_producto = parse_bool('mostrar_bloque_confianza_producto', False)
    config.mostrar_relacionados = parse_bool('mostrar_relacionados', True)
    config.mostrar_descuento_porcentaje = parse_bool('mostrar_descuento_porcentaje', True)
    if 'estilo_tienda' in data:
        config.estilo_tienda = clean_text('estilo_tienda') or 'moderno'

    if 'logo_file' in request.files:
        archivo_logo = request.files['logo_file']
        if archivo_logo and archivo_logo.filename:
            if not _ext_permitida(archivo_logo.filename):
                return jsonify({
                    'error': 'extension_logo_no_permitida',
                    'detalle': 'El logo debe estar en formato PNG, JPG, JPEG, WEBP o GIF.',
                }), 400
            upload_folder = os.path.join(current_app.static_folder, 'tienda_uploads', 'logos')
            try:
                nombre_final = procesar_y_guardar_imagen(
                    archivo_logo,
                    upload_folder,
                    prefijo=f"logo_{id_cliente}",
                    max_size=(640, 240),
                    calidad=92,
                    recortar_bordes=True,
                )
            except TypeError:
                nombre_final = procesar_y_guardar_imagen(
                    archivo_logo,
                    upload_folder,
                    prefijo=f"logo_{id_cliente}",
                    max_size=(640, 240),
                    calidad=92,
                )
            except PermissionError:
                return jsonify({'error': 'sin_permisos_uploads', 'detalle': 'No hay permisos de escritura en static/tienda_uploads'}), 500
            except ValueError:
                return jsonify({'error': 'imagen_invalida', 'detalle': 'La imagen del logo no se pudo procesar.'}), 400
            config.logo_url = f"/static/tienda_uploads/logos/{nombre_final}"
    elif 'logo_url' in data:
        config.logo_url = clean_text('logo_url')

    # Procesar archivo de portada si viene en la request
    if 'imagen_portada_file' in request.files:
        archivo = request.files['imagen_portada_file']
        if archivo and archivo.filename:
            if not _ext_permitida(archivo.filename):
                return jsonify({
                    'error': 'extension_portada_no_permitida',
                    'detalle': 'La portada debe estar en formato PNG, JPG, JPEG, WEBP o GIF.',
                }), 400
            upload_folder = os.path.join(current_app.static_folder, 'tienda_uploads', 'portadas')
            try:
                nombre_final = procesar_y_guardar_imagen(archivo, upload_folder, prefijo=f"portada_{id_cliente}")
            except PermissionError:
                return jsonify({'error': 'sin_permisos_uploads', 'detalle': 'No hay permisos de escritura en static/tienda_uploads'}), 500
            except ValueError:
                return jsonify({'error': 'imagen_invalida', 'detalle': 'La imagen de portada no se pudo procesar.'}), 400
            config.imagen_portada = f"/static/tienda_uploads/portadas/{nombre_final}"
    elif 'imagen_portada' in data:
        config.imagen_portada = clean_text('imagen_portada')

    db.session.commit()
    return jsonify({'ok': True, 'slug': config.slug})


@tienda_api_bp.route('/admin/producto/<int:id_producto>/imagenes', methods=['GET'])
@login_required
@requiere_permiso('editar_configuracion')
def admin_obtener_imagenes(id_producto: int):
    """Devuelve las imágenes de un producto para el panel admin."""
    p = Producto.query.get_or_404(id_producto)
    imagenes = ProductoImagen.query.filter_by(id_producto=p.id_producto).order_by(ProductoImagen.orden.asc()).all()
    return jsonify({
        'ok': True,
        'imagenes': [_serializar_imagen_tienda(img.to_dict()) for img in imagenes]
    })

@tienda_api_bp.route('/admin/imagen/<int:id_imagen>', methods=['DELETE'])
@login_required
@requiere_permiso('editar_configuracion')
def admin_eliminar_imagen(id_imagen: int):
    """Elimina una imagen de producto."""
    img = ProductoImagen.query.get_or_404(id_imagen)
    db.session.delete(img)
    db.session.commit()
    return jsonify({'ok': True})


@tienda_api_bp.route('/admin/imagen/<int:id_imagen>/rotar', methods=['POST'])
@login_required
@requiere_permiso('editar_configuracion')
def admin_rotar_imagen(id_imagen: int):
    """Rota una imagen ya subida y devuelve la URL versionada."""
    img = ProductoImagen.query.get_or_404(id_imagen)
    payload = request.get_json(silent=True) or {}

    try:
        grados = int(payload.get('grados', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'grados_invalidos'}), 400

    if grados not in (-270, -180, -90, 90, 180, 270):
        return jsonify({'error': 'rotacion_no_permitida'}), 400

    ruta_archivo = _resolver_ruta_media_tienda(img.url)
    if not ruta_archivo or not os.path.isfile(ruta_archivo):
        return jsonify({'error': 'imagen_no_encontrada'}), 404

    try:
        rotar_imagen_guardada(ruta_archivo, grados, calidad=80)
    except PermissionError:
        return jsonify({'error': 'sin_permisos_uploads'}), 500
    except ValueError:
        return jsonify({'error': 'imagen_invalida'}), 400

    try:
        generar_derivado_imagen(ruta_archivo)
    except (FileNotFoundError, PermissionError, ValueError):
        pass

    return jsonify({
        'ok': True,
        'imagen': _serializar_imagen_tienda(img.to_dict()),
    })

@tienda_api_bp.route('/admin/producto/<int:id_producto>/imagen', methods=['POST'])
@login_required
@requiere_permiso('editar_configuracion')
def admin_subir_imagen(id_producto: int):
    """Sube una imagen para un producto de tienda."""
    p = Producto.query.get_or_404(id_producto)

    if 'imagen' not in request.files:
        return jsonify({'error': 'imagen_requerida'}), 400

    archivo = request.files['imagen']
    if not archivo or not _ext_permitida(archivo.filename):
        return jsonify({'error': 'formato_no_permitido'}), 400

    upload_folder = os.path.join(
        current_app.static_folder, 'tienda_uploads', str(p.id_producto)
    )
    
    # Usar la nueva utilidad para procesar, optimizar y convertir a WebP
    try:
        nombre_final = procesar_y_guardar_imagen(
            archivo,
            upload_folder,
            prefijo=f"prod_{p.id_producto}",
            max_size=(1000, 1000),
            calidad=80,
            generar_card=True,
        )
    except PermissionError:
        return jsonify({'error': 'sin_permisos_uploads', 'detalle': 'No hay permisos de escritura en static/tienda_uploads'}), 500
    except ValueError:
        return jsonify({'error': 'imagen_invalida', 'detalle': 'La imagen subida no se pudo procesar.'}), 400

    url_relativa = f"/static/tienda_uploads/{p.id_producto}/{nombre_final}"
    orden_max = db.session.query(
        db.func.coalesce(db.func.max(ProductoImagen.orden), 0)
    ).filter_by(id_producto=p.id_producto).scalar()

    img = ProductoImagen(
        id_producto=p.id_producto,
        url=url_relativa,
        orden=orden_max + 1,
    )
    db.session.add(img)
    db.session.commit()

    return jsonify({
        'ok': True,
        'url': _serializar_imagen_tienda(img.to_dict()).get('url'),
        'id_imagen': img.id_imagen,
    }), 201
