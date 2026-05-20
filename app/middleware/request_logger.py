"""
Middleware para logging detallado de requests
"""
import os
import time
import logging
import uuid
from flask import request, g, current_app
from functools import wraps

from app.utils.perf import sanitize_server_timing_name

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = (
    'password',
    'token',
    'csrf',
    'secret',
    'authorization',
    'api_key',
    'apikey',
    'openai',
    'deepseek',
)

DEFAULT_VERBOSE_IGNORE_PATHS = (
    '/api/dashboard/totales',
    '/api/dashboard',
    '/api/notificaciones',
    '/whatsapp/webhook',
    '/caja/api/cola-cobro/resumen',
    '/gastos-corrientes/api/alertas/resumen',
    '/agenda/api/alertas/resumen',
    '/whatsapp/asesor/conversaciones',
    '/insights-diarios/api/hoy',
)

DEFAULT_ACCESS_IGNORE_PATHS = (
    '/caja/api/cola-cobro/resumen',
    '/gastos-corrientes/api/alertas/resumen',
    '/agenda/api/alertas/resumen',
    '/whatsapp/asesor/conversaciones',
    '/insights-diarios/api/hoy',
)

def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on', 'si', 'sí'}

def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in value.split(',') if p.strip()]

def _as_int(value: str | None, default: int) -> int:
    try:
        return int((value or '').strip())
    except Exception:
        return default

def _request_body_max_chars() -> int:
    return max(120, _as_int(os.environ.get('LOG_REQUEST_BODY_MAX_CHARS'), 600))

def _response_error_body_max_chars() -> int:
    return max(120, _as_int(os.environ.get('LOG_RESPONSE_ERROR_BODY_MAX_CHARS'), 400))

def _log_response_error_body() -> bool:
    return _is_truthy(os.environ.get('LOG_RESPONSE_ERROR_BODY', '0'))

def _should_ignore_path(path: str) -> bool:
    ignore_prefixes = _split_csv(os.environ.get('LOG_REQUEST_IGNORE_PATHS'))
    if not _is_truthy(os.environ.get('LOG_REQUEST_LOG_POLLING', '0')):
        ignore_prefixes.extend(DEFAULT_ACCESS_IGNORE_PATHS)
    for prefix in ignore_prefixes:
        if path.startswith(prefix):
            return True
    return False

def _should_ignore_verbose_path(path: str) -> bool:
    ignore_prefixes = _split_csv(os.environ.get('LOG_REQUEST_VERBOSE_IGNORE_PATHS'))
    ignore_prefixes.extend(DEFAULT_VERBOSE_IGNORE_PATHS)
    for prefix in ignore_prefixes:
        if path.startswith(prefix):
            return True
    return False

def _access_log_level() -> int:
    if _is_truthy(os.environ.get('LOG_REQUEST_ACCESS', '0')):
        return logging.INFO
    return logging.DEBUG

def _log_verbose() -> bool:
    return _is_truthy(os.environ.get('LOG_REQUEST_VERBOSE', '0'))

def _log_body() -> bool:
    return _is_truthy(os.environ.get('LOG_REQUEST_BODY', '0'))

def _request_slow_ms() -> int:
    return max(1, _as_int(os.environ.get('OBS_REQUEST_SLOW_MS'), 800))

def _request_query_count_warn() -> int:
    return max(1, _as_int(os.environ.get('OBS_REQUEST_QUERY_COUNT_WARN'), 20))

def _request_db_time_warn_ms() -> int:
    return max(1, _as_int(os.environ.get('OBS_REQUEST_DB_TIME_MS_WARN'), 400))

def _critical_endpoints() -> list[str]:
    configured = _split_csv(os.environ.get('OBS_CRITICAL_ENDPOINTS'))
    if configured:
        return configured
    return ['/dashboard', '/api/tienda', '/tienda', '/whatsapp', '/agenda']

def _is_critical_endpoint(path: str) -> bool:
    for prefix in _critical_endpoints():
        if path.startswith(prefix):
            return True
    return False

def _is_sensitive_key(key: str) -> bool:
    k = (key or '').lower()
    return any(s in k for s in SENSITIVE_KEYS)

def _safe_value(key: str, value):
    if _is_sensitive_key(key):
        return '***'
    if value is None:
        return None
    try:
        s = str(value)
    except Exception:
        return '<unprintable>'
    if len(s) > 300:
        return s[:300] + '…'
    return value

def _safe_mapping(data: dict | None):
    if not data:
        return {}
    out = {}
    for k, v in data.items():
        out[k] = _safe_value(k, v)
    return out

def _get_logger():
    try:
        return current_app.logger
    except Exception:
        return logger

def log_request_info():
    """Registra información detallada del request antes de procesarlo"""
    g.start_time = time.time()
    g.db_query_count = 0
    g.db_slow_query_count = 0
    g.db_query_elapsed_ms = 0.0
    g.perf_spans = []
    g.request_id = uuid.uuid4().hex[:10]
    
    # Información del cliente
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    # Información del request
    method = request.method
    path = request.path
    
    log = _get_logger()
    g.skip_access_log = _should_ignore_path(path)
    g.skip_verbose_log = _should_ignore_verbose_path(path)

    user_id = None
    username = None
    try:
        from flask_login import current_user
        if current_user and getattr(current_user, 'is_authenticated', False):
            user_id = getattr(current_user, 'id_usuario', None)
            username = getattr(current_user, 'username', None)
    except Exception:
        pass

    if not g.skip_access_log:
        log.log(_access_log_level(), f"[{g.request_id}] >>> REQUEST {method} {path}")
    if not _log_verbose():
        return
    if g.skip_access_log or g.skip_verbose_log:
        return

    access_level = _access_log_level()
    log.log(access_level, f"[{g.request_id}] Client IP: {client_ip}  User: {username or '-'} ({user_id or '-'})")
    log.log(access_level, f"[{g.request_id}] UA: {user_agent}")
    log.log(access_level, f"[{g.request_id}] Query: {request.query_string.decode('utf-8')}")
    log.log(access_level, f"[{g.request_id}] Content-Type: {request.headers.get('Content-Type', 'N/A')}")
    log.log(access_level, f"[{g.request_id}] Content-Length: {request.headers.get('Content-Length', 'N/A')}")
    log.log(access_level, f"[{g.request_id}] Referer: {request.headers.get('Referer', 'N/A')}")
    log.log(access_level, f"[{g.request_id}] X-Requested-With: {request.headers.get('X-Requested-With', 'N/A')}")

    if not _log_body():
        return

    if method in ['POST', 'PUT', 'PATCH']:
        try:
            if request.is_json:
                data = request.get_json()
                safe_data = _safe_mapping(data if isinstance(data, dict) else {'_json': str(data)})
                payload = str(safe_data)
                max_chars = _request_body_max_chars()
                if len(payload) > max_chars:
                    payload = payload[:max_chars] + '…'
                log.log(access_level, f"[{g.request_id}] JSON: {payload}")
            else:
                if request.form:
                    safe_form = _safe_mapping({k: request.form.get(k) for k in request.form.keys()})
                    payload = str(safe_form)
                    max_chars = _request_body_max_chars()
                    if len(payload) > max_chars:
                        payload = payload[:max_chars] + '…'
                    log.log(access_level, f"[{g.request_id}] Form: {payload}")
                elif request.files:
                    log.log(access_level, f"[{g.request_id}] Files: {list(request.files.keys())}")
        except Exception as e:
            log.warning(f"[{g.request_id}] No se pudo leer body: {e}")


def log_response_info(response):
    """Registra información de la respuesta"""
    if hasattr(g, 'start_time'):
        elapsed = time.time() - g.start_time
        log = _get_logger()
        location = None
        try:
            location = response.headers.get('Location')
        except Exception:
            location = None

        req_id = getattr(g, 'request_id', '-')
        try:
            method = request.method
            path = request.path
        except Exception:
            method = '-'
            path = '-'

        if not getattr(g, 'skip_access_log', False) and not _should_ignore_path(path):
            access_level = _access_log_level()
            log.log(
                access_level,
                f"[{req_id}] <<< RESPONSE {response.status_code} {elapsed:.3f}s  {method} {path}  CT: {getattr(response, 'content_type', '')}",
            )
            if location:
                log.log(access_level, f"[{req_id}] Location: {location}")
            elapsed_ms = elapsed * 1000
            query_count = int(getattr(g, 'db_query_count', 0) or 0)
            slow_query_count = int(getattr(g, 'db_slow_query_count', 0) or 0)
            db_time_ms = float(getattr(g, 'db_query_elapsed_ms', 0.0) or 0.0)
            perf_spans = list(getattr(g, 'perf_spans', []) or [])
            server_timing_parts = [
                f"total;dur={elapsed_ms:.1f}",
                f"db;dur={db_time_ms:.1f};desc=\"{query_count} queries\"",
            ]
            for span in perf_spans:
                span_name = sanitize_server_timing_name(span.get('name'))
                span_duration = max(0.0, float(span.get('duration_ms', 0.0) or 0.0))
                server_timing_parts.append(f"{span_name};dur={span_duration:.1f}")
            response.headers['Server-Timing'] = ', '.join(server_timing_parts)
            response.headers['X-DB-Query-Count'] = str(query_count)
            response.headers['X-DB-Time-Ms'] = f"{db_time_ms:.1f}"
            response.headers['X-Request-ID'] = str(req_id)
            if (
                elapsed_ms >= _request_slow_ms()
                or _is_critical_endpoint(path)
                or query_count >= _request_query_count_warn()
                or db_time_ms >= _request_db_time_warn_ms()
            ):
                endpoint = getattr(request, 'endpoint', None) or '-'
                log.log(
                    access_level,
                    f"[{req_id}] REQUEST_METRIC endpoint={endpoint} path={path} method={method} status={response.status_code} duration_ms={elapsed_ms:.1f} db_queries={query_count} db_slow_queries={slow_query_count} db_time_ms={db_time_ms:.1f}",
                )
        
        if response.status_code == 404:
            log.log(_access_log_level(), f"[{req_id}] Client error 404  {method} {path}")
        elif 400 <= response.status_code < 500:
            log.warning(f"[{req_id}] Client error {response.status_code}  {method} {path}")
        elif response.status_code >= 500:
            try:
                if _log_response_error_body():
                    max_chars = _response_error_body_max_chars()
                    body = response.get_data(as_text=True)[:max_chars]
                    log.error(f"[{req_id}] Server error body: {body}")
            except Exception:
                pass
    
    return response


def log_database_operation(operation, model, data=None, error=None):
    """Helper para loguear operaciones de base de datos"""
    if error:
        logger.error(f"DB ERROR - {operation} {model}: {error}")
        logger.error(f"Data: {data}")
    else:
        logger.info(f"DB SUCCESS - {operation} {model}")
        if data:
            logger.debug(f"Data: {data}")


def log_route(func):
    """Decorator para loguear entrada/salida de rutas específicas"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f">>> Entering route: {func.__name__}")
        try:
            result = func(*args, **kwargs)
            logger.info(f"<<< Exiting route: {func.__name__} - SUCCESS")
            return result
        except Exception as e:
            logger.error(f"<<< Exiting route: {func.__name__} - ERROR: {e}")
            raise
    return wrapper
