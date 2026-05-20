"""
Tools de verdad operativa para el asistente web de tienda.
"""
import re
import unicodedata
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import current_app

from app import db
from app.models.producto import Categoria, Producto
from app.services.tienda_promociones import (
    attach_promotion_to_product_data,
    get_active_product_promotion_map,
)
from app.services.tienda_scope import public_product_query
from app.utils.tienda_urls import build_product_public_path


SEARCH_STOPWORDS = {
    'a', 'al', 'con', 'cual', 'cuales', 'cuanto', 'cuantos', 'cuesta', 'cuestan',
    'de', 'del', 'el', 'en', 'hay', 'la', 'las', 'lo', 'los', 'me', 'mostrar',
    'mostrame', 'necesito', 'para', 'que', 'queria', 'quiero', 'tienen', 'tenes',
    'tiene', 'un', 'una', 'uno', 'unas', 'unos', 'ver',
}
DAY_TO_WEEKDAY = {
    'lunes': 0,
    'martes': 1,
    'miercoles': 2,
    'miércoles': 2,
    'jueves': 3,
    'viernes': 4,
    'sabado': 5,
    'sábado': 5,
    'domingo': 6,
}
WEEKDAY_TO_NAME = {
    0: 'lunes',
    1: 'martes',
    2: 'miércoles',
    3: 'jueves',
    4: 'viernes',
    5: 'sábado',
    6: 'domingo',
}
MONTH_TO_NAME = {
    1: 'enero',
    2: 'febrero',
    3: 'marzo',
    4: 'abril',
    5: 'mayo',
    6: 'junio',
    7: 'julio',
    8: 'agosto',
    9: 'septiembre',
    10: 'octubre',
    11: 'noviembre',
    12: 'diciembre',
}
TIME_RE = re.compile(r'(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?', re.IGNORECASE)
DAY_RANGE_RE = re.compile(
    r'(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)\s+a\s+'
    r'(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)',
    re.IGNORECASE,
)


def _normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    without_marks = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_marks.lower().strip()


def _extract_search_terms(value: str) -> list[str]:
    tokens = re.findall(r'[a-z0-9]+', _normalize_text(value))
    terms = []
    seen = set()
    for token in tokens:
        if len(token) < 2 or token in SEARCH_STOPWORDS or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def _decimal_to_float(value) -> float:
    if isinstance(value, Decimal):
        return float(value)
    if value in (None, ''):
        return 0.0
    return float(value)


def _timezone_name() -> str:
    return (
        current_app.config.get('TIMEZONE')
        or current_app.config.get('APP_TIMEZONE')
        or 'America/Asuncion'
    )


def _zoneinfo() -> ZoneInfo:
    try:
        return ZoneInfo(_timezone_name())
    except Exception:
        return ZoneInfo('America/Asuncion')


def _now_local() -> datetime:
    return datetime.now(_zoneinfo())


def _to_local_date(value: date | datetime | None = None) -> date:
    if value is None:
        return _now_local().date()
    if isinstance(value, datetime):
        return value.astimezone(_zoneinfo()).date() if value.tzinfo else value.date()
    return value


def _format_date_long(value: date) -> str:
    return f'{value.day} de {MONTH_TO_NAME[value.month]} de {value.year}'


def _format_time_short(value: time | None) -> str:
    if value is None:
        return ''
    return f'{value.hour:02d}:{value.minute:02d}'


def _serialize_relative_date(value: date, label: str) -> dict:
    weekday = WEEKDAY_TO_NAME[value.weekday()]
    return {
        'referencia': label,
        'fecha': value.isoformat(),
        'fecha_larga': _format_date_long(value),
        'dia_semana': weekday,
        'es_fin_de_semana': value.weekday() >= 5,
        'timezone': _timezone_name(),
    }


def _parse_time_token(raw_value: str) -> time | None:
    match = TIME_RE.search(str(raw_value or ''))
    if not match:
        return None
    hour = int(match.group('hour') or 0)
    minute = int(match.group('minute') or 0)
    ampm = (match.group('ampm') or '').lower()
    if ampm == 'am' and hour == 12:
        hour = 0
    elif ampm == 'pm' and 1 <= hour <= 11:
        hour += 12
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return time(hour=hour, minute=minute)


def _expand_day_range(start_label: str, end_label: str) -> set[int]:
    start = DAY_TO_WEEKDAY[_normalize_text(start_label)]
    end = DAY_TO_WEEKDAY[_normalize_text(end_label)]
    days = {start}
    cursor = start
    while cursor != end:
        cursor = (cursor + 1) % 7
        days.add(cursor)
    return days


def _parse_days(schedule_text: str) -> set[int]:
    normalized = _normalize_text(schedule_text)
    if not normalized:
        return set()
    if 'lunes a domingo' in normalized or 'todos los dias' in normalized or 'todos los dias' in normalized:
        return set(range(7))

    days = set()
    for match in DAY_RANGE_RE.finditer(normalized):
        days.update(_expand_day_range(match.group(1), match.group(2)))
    for label, weekday in DAY_TO_WEEKDAY.items():
        if re.search(rf'\b{re.escape(_normalize_text(label))}\b', normalized):
            days.add(weekday)
    return days


def _parse_schedule(schedule_text: str) -> dict:
    normalized = _normalize_text(schedule_text)
    matches = list(TIME_RE.finditer(normalized))
    opening = _parse_time_token(matches[0].group(0)) if matches else None
    closing = _parse_time_token(matches[1].group(0)) if len(matches) > 1 else None
    days = _parse_days(normalized)
    parsed = bool(opening and closing and days)
    return {
        'parsed': parsed,
        'days': days or set(range(7)),
        'opening': opening,
        'closing': closing,
        'raw': schedule_text or '',
    }


def _resolve_schedule(contexto: dict) -> str:
    assistant_context = contexto.get('assistant_context') or {}
    faq = assistant_context.get('faq') or {}
    return (faq.get('horarios') or '').strip()


def _resolve_target_date(args: dict | None = None) -> tuple[date, str]:
    args = args or {}
    if (args.get('fecha') or '').strip():
        fecha = date.fromisoformat((args.get('fecha') or '').strip())
        return fecha, 'fecha'

    referencia = _normalize_text(args.get('referencia') or args.get('momento') or 'ahora')
    today = _to_local_date()
    if referencia in {'manana', 'mañana'}:
        return today + timedelta(days=1), 'mañana'
    if referencia in {'pasado_manana', 'pasado mañana'}:
        return today + timedelta(days=2), 'pasado mañana'
    if referencia == 'ayer':
        return today - timedelta(days=1), 'ayer'
    return today, 'hoy'


def _evaluate_schedule(schedule_text: str, target_date: date, *, now_local: datetime | None = None) -> dict:
    parsed = _parse_schedule(schedule_text)
    day_name = WEEKDAY_TO_NAME[target_date.weekday()]
    result = {
        'fecha': target_date.isoformat(),
        'fecha_larga': _format_date_long(target_date),
        'dia_semana': day_name,
        'timezone': _timezone_name(),
        'horario_texto': schedule_text or '',
        'abierta': None,
        'aplica_ese_dia': None,
        'abre': '',
        'cierra': '',
        'mensaje': '',
        'schedule_parsed': parsed['parsed'],
    }
    if not schedule_text:
        result['mensaje'] = 'No hay horario cargado.'
        return result

    if not parsed['parsed']:
        result['mensaje'] = f'Horario informado: {schedule_text}'
        return result

    result['abre'] = _format_time_short(parsed['opening'])
    result['cierra'] = _format_time_short(parsed['closing'])
    applies_today = target_date.weekday() in parsed['days']
    result['aplica_ese_dia'] = applies_today

    if not applies_today:
        result['abierta'] = False
        result['mensaje'] = f'El {day_name} no atiende según el horario cargado.'
        return result

    if now_local is None:
        now_local = _now_local()
    if target_date == now_local.date():
        current_time = now_local.timetz().replace(tzinfo=None)
        result['abierta'] = parsed['opening'] <= current_time <= parsed['closing']
        estado = 'abierta' if result['abierta'] else 'cerrada'
        result['mensaje'] = (
            f'Ahora mismo la tienda está {estado}. '
            f'Horario de hoy: {result["abre"]} a {result["cierra"]}.'
        )
        return result

    result['abierta'] = None
    result['mensaje'] = f'El {day_name} atiende de {result["abre"]} a {result["cierra"]}.'
    return result


def _serialize_product_match(producto: Producto, slug: str, promotion_map: dict | None = None) -> dict:
    promotion_map = promotion_map or {}
    base = {
        'id': producto.id_producto,
        'nombre': producto.nombre,
        'codigo': producto.codigo,
        'precio': _decimal_to_float(producto.precio_venta),
        'precio_anterior': _decimal_to_float(producto.precio_anterior_tienda),
        'stock_actual': int(producto.stock_actual or 0),
        'disponible': bool((producto.stock_actual or 0) > 0),
        'stock_bajo': bool(producto.stock_bajo),
        'marca': producto.marca or '',
        'modelo': producto.modelo or '',
        'categoria': producto.categoria.nombre if producto.categoria else '',
        'url': build_product_public_path(slug, producto.id_producto, producto.nombre),
        'promocion_activa': None,
    }
    return attach_promotion_to_product_data(
        producto,
        base,
        promotion_map.get(producto.id_producto),
        allow_discount_percentage=True,
    )


def _find_products(config, slug: str, busqueda: str, limit: int = 5) -> list[dict]:
    terms = _extract_search_terms(busqueda)
    query = public_product_query(config).outerjoin(Categoria)
    if terms:
        conditions = []
        for term in terms:
            pattern = f'%{term}%'
            conditions.extend([
                Producto.nombre.ilike(pattern),
                Producto.marca.ilike(pattern),
                Producto.modelo.ilike(pattern),
                Producto.descripcion_tienda.ilike(pattern),
                Producto.descripcion.ilike(pattern),
                Categoria.nombre.ilike(pattern),
            ])
        query = query.filter(db.or_(*conditions))
    elif (busqueda or '').strip():
        pattern = f"%{_normalize_text(busqueda)}%"
        query = query.filter(
            db.or_(
                Producto.nombre.ilike(pattern),
                Producto.marca.ilike(pattern),
                Producto.modelo.ilike(pattern),
                Producto.descripcion_tienda.ilike(pattern),
                Producto.descripcion.ilike(pattern),
                Categoria.nombre.ilike(pattern),
            )
        )
    productos = query.distinct().order_by(
        Producto.es_destacado_tienda.desc(),
        Producto.vistas_tienda.desc(),
        Producto.nombre.asc(),
    ).limit(max(1, limit)).all()
    promotion_map = get_active_product_promotion_map(
        int(config.id_cliente),
        [item.id_producto for item in productos],
    )
    return [_serialize_product_match(item, slug, promotion_map) for item in productos]


def obtener_fecha_hora_actual(_args: dict, _contexto: dict) -> dict:
    now_local = _now_local()
    return {
        'fecha': now_local.date().isoformat(),
        'hora': now_local.strftime('%H:%M'),
        'dia_semana': WEEKDAY_TO_NAME[now_local.weekday()],
        'fecha_larga': _format_date_long(now_local.date()),
        'timestamp_iso': now_local.isoformat(),
        'timezone': _timezone_name(),
    }


def obtener_calendario_relativo(args: dict, _contexto: dict) -> dict:
    referencia = _normalize_text(args.get('referencia') or 'hoy')
    today = _to_local_date()
    if referencia in {'manana', 'mañana'}:
        return _serialize_relative_date(today + timedelta(days=1), 'mañana')
    if referencia in {'pasado_manana', 'pasado mañana'}:
        return _serialize_relative_date(today + timedelta(days=2), 'pasado mañana')
    if referencia == 'ayer':
        return _serialize_relative_date(today - timedelta(days=1), 'ayer')
    if referencia in {'este_fin_de_semana', 'este fin de semana'}:
        saturday_offset = (5 - today.weekday()) % 7
        saturday = today + timedelta(days=saturday_offset)
        sunday = saturday + timedelta(days=1)
        return {
            'referencia': 'este fin de semana',
            'desde': _serialize_relative_date(saturday, 'sábado'),
            'hasta': _serialize_relative_date(sunday, 'domingo'),
            'timezone': _timezone_name(),
        }
    return _serialize_relative_date(today, 'hoy')


def obtener_estado_tienda_actual(args: dict, contexto: dict) -> dict:
    schedule_text = _resolve_schedule(contexto)
    target_date, referencia = _resolve_target_date(args)
    result = _evaluate_schedule(schedule_text, target_date)
    result['referencia'] = referencia
    return result


def obtener_info_contacto_actual(args: dict, contexto: dict) -> dict:
    assistant_context = contexto.get('assistant_context') or {}
    tienda = assistant_context.get('tienda') or {}
    faq = assistant_context.get('faq') or {}
    bot_context = assistant_context.get('contexto_bot') or {}
    public_config = contexto['config'].to_public_dict()
    canal = _normalize_text(args.get('canal') or 'todos')

    payload = {
        'whatsapp': tienda.get('telefono_whatsapp') or '',
        'telefono': bot_context.get('telefonos_contacto') or faq.get('contacto') or '',
        'email': public_config.get('email_contacto') or '',
        'direccion': faq.get('ubicacion') or bot_context.get('direccion') or '',
        'sitio_web': public_config.get('sitio_web') or '',
        'redes': {
            'instagram': public_config.get('instagram_url') or '',
            'facebook': public_config.get('facebook_url') or '',
            'youtube': public_config.get('youtube_url') or '',
        },
    }
    if canal == 'todos':
        return payload
    return {'canal': canal, 'valor': payload.get(canal) or ''}


def obtener_stock_preciso_producto(args: dict, contexto: dict) -> dict:
    busqueda = (args.get('busqueda') or '').strip()
    productos = _find_products(contexto['config'], contexto['slug'], busqueda, limit=3)
    return {
        'busqueda': busqueda,
        'total': len(productos),
        'productos': [
            {
                'id': item['id'],
                'nombre': item['nombre'],
                'codigo': item['codigo'],
                'stock_actual': item['stock_actual'],
                'disponible': item['disponible'],
                'stock_bajo': item['stock_bajo'],
                'url': item['url'],
            }
            for item in productos
        ],
    }


def obtener_precio_preciso_producto(args: dict, contexto: dict) -> dict:
    busqueda = (args.get('busqueda') or '').strip()
    productos = _find_products(contexto['config'], contexto['slug'], busqueda, limit=3)
    return {
        'busqueda': busqueda,
        'total': len(productos),
        'productos': [
            {
                'id': item['id'],
                'nombre': item['nombre'],
                'codigo': item['codigo'],
                'precio': item['precio'],
                'precio_anterior': item['precio_anterior'],
                'promocion_activa': item.get('promocion_activa'),
                'es_oferta': bool(item.get('es_oferta')),
                'url': item['url'],
            }
            for item in productos
        ],
    }


def obtener_metodos_pago_vigentes(_args: dict, contexto: dict) -> dict:
    assistant_context = contexto.get('assistant_context') or {}
    faq = assistant_context.get('faq') or {}
    return {
        'metodos_pago': faq.get('metodos_pago') or '',
        'timezone': _timezone_name(),
    }


def obtener_envio_estimado(args: dict, contexto: dict) -> dict:
    assistant_context = contexto.get('assistant_context') or {}
    faq = assistant_context.get('faq') or {}
    zona = (args.get('zona') or '').strip()
    return {
        'zona_consultada': zona,
        'envios': faq.get('envios') or '',
        'zonas_de_entrega': faq.get('zonas_de_entrega') or '',
        'cobertura': faq.get('cobertura') or '',
        'mensaje': 'La estimación exacta depende de la zona y la confirmación humana.' if zona else '',
    }


def obtener_contexto_temporal_local(args: dict, contexto: dict) -> dict:
    target_date, referencia = _resolve_target_date(args)
    schedule_text = _resolve_schedule(contexto)
    schedule_status = _evaluate_schedule(schedule_text, target_date)
    return {
        'referencia': referencia,
        'fecha': target_date.isoformat(),
        'fecha_larga': _format_date_long(target_date),
        'dia_semana': WEEKDAY_TO_NAME[target_date.weekday()],
        'es_fin_de_semana': target_date.weekday() >= 5,
        'horario_tienda': schedule_status,
        'timezone': _timezone_name(),
    }


def obtener_politicas_publicas(args: dict, contexto: dict) -> dict:
    assistant_context = contexto.get('assistant_context') or {}
    faq = assistant_context.get('faq') or {}
    tema = _normalize_text(args.get('tema') or 'todos')
    payload = {
        'garantia': faq.get('garantia') or '',
        'politica_cambios': faq.get('politica_cambios') or '',
        'retiro_local': faq.get('retiro_local') or '',
        'envios': faq.get('envios') or '',
        'cobertura': faq.get('cobertura') or '',
    }
    if tema == 'todos':
        return payload
    return {'tema': tema, 'valor': payload.get(tema) or ''}
