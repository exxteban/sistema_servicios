"""
Decoradores y utilidades comunes
"""
from functools import wraps
from datetime import datetime, timezone, date, time, timedelta
from zoneinfo import ZoneInfo
import unicodedata
from flask import redirect, url_for, flash, current_app, jsonify, request
from flask_login import current_user


def normalize_for_thermal_printer(text):
    """
    Normaliza texto para impresoras térmicas que no soportan caracteres Unicode.
    Convierte caracteres acentuados a su equivalente ASCII.
    Por ejemplo: á->a, é->e, ñ->n, etc.
    """
    if not text:
        return text
    
    # Mapeo específico para caracteres problemáticos
    char_map = {
        'á': 'a', 'à': 'a', 'ä': 'a', 'â': 'a', 'ã': 'a',
        'é': 'e', 'è': 'e', 'ë': 'e', 'ê': 'e',
        'í': 'i', 'ì': 'i', 'ï': 'i', 'î': 'i',
        'ó': 'o', 'ò': 'o', 'ö': 'o', 'ô': 'o', 'õ': 'o',
        'ú': 'u', 'ù': 'u', 'ü': 'u', 'û': 'u',
        'ñ': 'n', 'Ñ': 'N',
        'Á': 'A', 'À': 'A', 'Ä': 'A', 'Â': 'A', 'Ã': 'A',
        'É': 'E', 'È': 'E', 'Ë': 'E', 'Ê': 'E',
        'Í': 'I', 'Ì': 'I', 'Ï': 'I', 'Î': 'I',
        'Ó': 'O', 'Ò': 'O', 'Ö': 'O', 'Ô': 'O', 'Õ': 'O',
        'Ú': 'U', 'Ù': 'U', 'Ü': 'U', 'Û': 'U',
        '₲': 'Gs', '€': 'EUR', '$': '$', '¢': 'c',
        '°': 'o', '©': '(c)', '®': '(R)', '™': '(TM)',
        '–': '-', '—': '-', '‘': "'", '’': "'", '“': '"', '”': '"',
    }
    
    result = str(text)
    for original, replacement in char_map.items():
        result = result.replace(original, replacement)
    
    # Normalizar cualquier otro carácter Unicode restante
    try:
        result = unicodedata.normalize('NFKD', result)
        result = result.encode('ascii', 'ignore').decode('ascii')
    except Exception:
        pass
    
    return result


def admin_required(f):
    """Decorador que requiere rol de administrador"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.es_admin():
            if bool(getattr(current_user, 'modo_demo', False)):
                flash('Modo demo: esta acción está deshabilitada.', 'warning')
            else:
                flash('Acceso denegado. Se requiere rol de administrador.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def supervisor_required(f):
    """Decorador que requiere rol de supervisor o admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.es_supervisor():
            if bool(getattr(current_user, 'modo_demo', False)):
                flash('Modo demo: esta acción está deshabilitada.', 'warning')
            else:
                flash('Acceso denegado. Se requiere rol de supervisor.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def caja_abierta_required(f):
    """Decorador que requiere tener una caja abierta"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.models import SesionCaja
        sesion = SesionCaja.query.filter_by(
            id_usuario=current_user.id_usuario,
            estado='abierta'
        ).first()
        if not sesion:
            mensaje = 'Debe abrir una caja antes de realizar esta operación.'
            accept = (request.headers.get('Accept') or '').lower()
            x_requested_with = (request.headers.get('X-Requested-With') or '').lower()
            if (
                request.is_json
                or 'application/json' in accept
                or x_requested_with == 'xmlhttprequest'
                or request.path.startswith('/api/')
            ):
                return jsonify({
                    'error': mensaje,
                    'redirect_url': url_for('caja.abrir'),
                    'requiere_caja_abierta': True,
                }), 400
            flash(mensaje, 'warning')
            return redirect(url_for('caja.abrir'))
        return f(*args, **kwargs)
    return decorated_function


def formatear_moneda(valor, con_simbolo=True):
    """Formatea un valor como moneda (Guaraníes)"""
    try:
        valor = float(valor or 0)
        formateado = "{:,.0f}".format(valor).replace(",", ".")
        if con_simbolo:
            return f"₲ {formateado}"
        return formateado
    except (ValueError, TypeError):
        return "₲ 0" if con_simbolo else "0"


# ── Moneda configurable por empresa (símbolo, decimales, separadores) ─────────
# Los defaults reproducen el formato guaraní actual, así nada cambia en Paraguay.
# Para Brasil se configura: R$, 2 decimales, miles '.', decimal ',', locale 'pt-BR'.
_MONEDA_DEFAULTS = {
    'simbolo': '₲',
    'decimales': 0,
    'sep_miles': '.',
    'sep_decimal': ',',
    'locale': 'es-PY',
}


def config_moneda():
    """Lee (y cachea por request) la configuración de moneda de la empresa."""
    from flask import g, has_request_context

    if has_request_context() and hasattr(g, '_config_moneda'):
        return g._config_moneda

    cfg = dict(_MONEDA_DEFAULTS)
    try:
        from app.models import Configuracion
        cfg['simbolo'] = (Configuracion.obtener('moneda_simbolo') or cfg['simbolo'])
        cfg['decimales'] = Configuracion.obtener_int('moneda_decimales', cfg['decimales'])
        cfg['sep_miles'] = (Configuracion.obtener('moneda_sep_miles') or cfg['sep_miles'])
        cfg['sep_decimal'] = (Configuracion.obtener('moneda_sep_decimal') or cfg['sep_decimal'])
        cfg['locale'] = (Configuracion.obtener('moneda_locale') or cfg['locale'])
    except Exception:
        pass

    if cfg['decimales'] < 0:
        cfg['decimales'] = 0

    if has_request_context():
        g._config_moneda = cfg
    return cfg


def formato_moneda_local(valor, con_simbolo=True):
    """Formatea un importe según la moneda configurada (símbolo/decimales/separadores)."""
    cfg = config_moneda()
    try:
        valor = float(valor or 0)
    except (ValueError, TypeError):
        valor = 0.0

    dec = cfg['decimales']
    # Python formatea con ',' para miles y '.' para decimales; luego mapeamos a
    # los separadores configurados usando un placeholder para no pisarlos.
    base = "{:,.{dec}f}".format(valor, dec=dec)
    base = (
        base.replace(',', '\x00')
        .replace('.', cfg['sep_decimal'])
        .replace('\x00', cfg['sep_miles'])
    )
    if con_simbolo:
        return f"{cfg['simbolo']} {base}"
    return base


def formatear_fecha(fecha, formato='%d/%m/%Y'):
    """Formatea una fecha"""
    if fecha:
        return fecha.strftime(formato)
    return ''


def formatear_fecha_hora(fecha, formato='%d/%m/%Y %H:%M'):
    """Formatea fecha y hora"""
    if fecha:
        return fecha.strftime(formato)
    return ''


def get_app_timezone_name(default='America/Asuncion'):
    try:
        return current_app.config.get('TIMEZONE') or default
    except Exception:
        return default


def get_app_timezone():
    tz_name = get_app_timezone_name()
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo('UTC')


def now_local():
    return datetime.now(get_app_timezone())


def utc_naive_to_local(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_app_timezone())


def local_strftime(dt, fmt='%d/%m/%Y %H:%M'):
    local_dt = utc_naive_to_local(dt)
    if not local_dt:
        return ''
    return local_dt.strftime(fmt)


def today_local():
    return now_local().date()


def utc_bounds_for_local_dates(start_date: date, end_date: date):
    tz = get_app_timezone()
    start_local_dt = datetime.combine(start_date, time.min, tzinfo=tz)
    end_local_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    start_utc = start_local_dt.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local_dt.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except Exception:
        return None
