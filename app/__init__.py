"""
Inicialización de la aplicación Flask
Sistema de Inventario y Ventas
"""
import os
import re
import sqlite3
import time
import traceback
from functools import lru_cache
from flask import Flask, request, jsonify, redirect, url_for, flash, g, has_request_context
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.exceptions import MethodNotAllowed, RequestEntityTooLarge
from config import config
from app.bootstrap.runtime import register_runtime_features
from app.bootstrap.schema import initialize_database
from app.extensions import cache

# Extensiones
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor inicie sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'

@lru_cache(maxsize=512)
def _sqlite_re_compile(pattern: str):
    try:
        return re.compile(pattern)
    except Exception:
        return None


def _sqlite_regexp(pattern, value):
    if pattern is None or value is None:
        return 0
    compiled = _sqlite_re_compile(str(pattern))
    if not compiled:
        return 0
    return 1 if compiled.search(str(value)) else 0


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        try:
            dbapi_connection.create_function("regexp", 2, _sqlite_regexp)
        except Exception:
            pass


def create_app(config_name='default'):
    """Factory de la aplicación"""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    def _wants_json() -> bool:
        try:
            if (request.path or '').startswith('/api/'):
                return True
        except Exception:
            pass
        try:
            if request.is_json:
                return True
        except Exception:
            pass
        try:
            if (request.content_type or '').startswith('application/json'):
                return True
        except Exception:
            pass
        try:
            if (request.headers.get('X-Requested-With') or '') == 'XMLHttpRequest':
                return True
        except Exception:
            pass
        try:
            if 'application/json' in (request.headers.get('Accept') or ''):
                return True
        except Exception:
            pass
        try:
            if request.accept_mimetypes.best == 'application/json':
                return True
        except Exception:
            pass
        return False

    def _is_truthy_env(name: str, default: str = '0') -> bool:
        raw = os.environ.get(name, default)
        return (raw or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on', 'si', 'sí'}

    def _as_int_env(name: str, default: int) -> int:
        raw = os.environ.get(name)
        if raw is None:
            return default
        try:
            return int(raw.strip())
        except Exception:
            return default

    proxy_fix = os.environ.get('USE_PROXY_FIX')
    if proxy_fix and proxy_fix.strip().lower() not in {'0', 'false', 'no', 'n', 'off'}:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
    
    # Inicializar extensiones
    app.config.setdefault('CACHE_TYPE', os.environ.get('CACHE_TYPE', 'SimpleCache'))
    app.config.setdefault('CACHE_DEFAULT_TIMEOUT', _as_int_env('CACHE_DEFAULT_TIMEOUT', 300))
    cache_redis_url = os.environ.get('CACHE_REDIS_URL')
    if cache_redis_url:
        app.config.setdefault('CACHE_REDIS_URL', cache_redis_url)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)

    @app.before_request
    def _reset_login_user_cache():
        g.pop('_login_user', None)

    @app.before_request
    def _enforce_demo_session_limit():
        from app.services.demo_session_guard import enforce_demo_session_limit

        return enforce_demo_session_limit()

    @login_manager.unauthorized_handler
    def _unauthorized():
        if _wants_json():
            return jsonify({'error': 'auth', 'mensaje': 'Sesión expirada. Inicie sesión nuevamente.'}), 401
        next_url = (request.full_path or request.path or '/').rstrip('?')
        flash(login_manager.login_message, login_manager.login_message_category)
        return redirect(url_for('auth.login', next=next_url))

    # Configuración de Logging
    import logging
    from logging.handlers import WatchedFileHandler

    log_level_name = (os.environ.get('LOG_LEVEL') or ('DEBUG' if app.config.get('DEBUG') else 'INFO')).upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    
    # Intentar configurar logging a archivo, pero no fallar si no hay permisos
    try:
        if not os.path.exists('logs'):
            os.mkdir('logs')

        file_handler = WatchedFileHandler('logs/sistema.log')
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(log_level)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(log_level)
        app.logger.info('Sistema de Inventario iniciado')
    except (PermissionError, OSError) as e:
        # Si no se puede escribir en archivo, usar solo stderr
        app.logger.setLevel(log_level)
        app.logger.warning(f'No se pudo configurar logging a archivo: {e}. Usando solo stderr.')
        # Configurar handler de consola
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s'
        ))
        console_handler.setLevel(log_level)
        app.logger.addHandler(console_handler)

    try:
        root = logging.getLogger()
        root.setLevel(log_level)
        for h in list(app.logger.handlers):
            if h not in root.handlers:
                root.addHandler(h)
        app.logger.propagate = False

        if log_level > logging.DEBUG:
            for name in ('httpx', 'openai', 'urllib3', 'requests'):
                logging.getLogger(name).setLevel(logging.WARNING)
    except Exception:
        pass

    @app.teardown_request
    def log_teardown_request(error=None):
        if not error:
            return
        req_id = getattr(g, 'request_id', None)
        prefix = f'[{req_id}] ' if req_id else ''
        app.logger.error(
            f"{prefix}Unhandled exception in request: {error}",
            exc_info=(type(error), error, error.__traceback__),
        )
        statement = getattr(error, 'statement', None)
        params = getattr(error, 'params', None)
        if statement:
            app.logger.error(f"{prefix}SQL statement: {statement}")
        if params:
            app.logger.error(f"{prefix}SQL params: {params}")
        original = getattr(error, 'orig', None)
        if original:
            app.logger.error(f"{prefix}DBAPI original: {original}")
        if not getattr(error, '__traceback__', None):
            formatted = ''.join(traceback.format_stack(limit=20))
            app.logger.error(f"{prefix}Stack fallback:\n{formatted}")


    if config_name == 'production':
        secret = app.config.get('SECRET_KEY')
        if not secret or secret == 'clave-secreta-cambiar-en-produccion':
            raise RuntimeError('SECRET_KEY debe estar configurado en producción')

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        req_id = getattr(g, 'request_id', None)
        prefix = f'[{req_id}] ' if req_id else ''
        app.logger.warning(f"{prefix}CSRFError: {getattr(e, 'description', str(e))}")
        if _wants_json():
            return jsonify({'error': 'csrf', 'mensaje': 'Token CSRF inválido o faltante.'}), 400
        flash('Sesión expirada o solicitud inválida. Recargue la página e intente nuevamente.', 'warning')
        return redirect(request.referrer or url_for('auth.login'))

    @app.errorhandler(MethodNotAllowed)
    def handle_method_not_allowed(e):
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'method_not_allowed', 'mensaje': 'La acción no está permitida para esta URL.'}), 405
        flash('La acción no está permitida para esta URL.', 'danger')
        return redirect(request.referrer or url_for('main.dashboard')), 303

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(_e):
        if _wants_json():
            return jsonify({'error': 'request_too_large', 'mensaje': 'Solicitud demasiado grande.'}), 413
        flash('Solicitud demasiado grande.', 'danger')
        return redirect(request.referrer or url_for('main.dashboard')), 303
    
    # Middleware de logging de requests
    from app.middleware import log_request_info, log_response_info
    polling_log_ignore = (
        '/caja/api/cola-cobro/resumen,'
        '/gastos-corrientes/api/alertas/resumen,'
        '/agenda/api/alertas/resumen,'
        '/whatsapp/asesor/conversaciones,'
        '/insights-diarios/api/hoy'
    )
    os.environ.setdefault('LOG_REQUEST_IGNORE_PATHS', polling_log_ignore)
    os.environ.setdefault(
        'LOG_REQUEST_VERBOSE_IGNORE_PATHS',
        '/api/dashboard/totales,/api/dashboard,/api/notificaciones,/whatsapp/webhook,'
        f'{polling_log_ignore}',
    )
    os.environ.setdefault('LOG_RESPONSE_ERROR_BODY', '0')
    os.environ.setdefault('LOG_RESPONSE_ERROR_BODY_MAX_CHARS', '400')
    os.environ.setdefault('LOG_REQUEST_BODY_MAX_CHARS', '600')
    os.environ.setdefault('OBS_REQUEST_QUERY_COUNT_WARN', '20')
    os.environ.setdefault('OBS_REQUEST_DB_TIME_MS_WARN', '400')

    app.logger.info(
        "Log policy access=%s verbose=%s body=%s verbose_ignore=%s error_body=%s",
        os.environ.get('LOG_REQUEST_ACCESS', '0'),
        os.environ.get('LOG_REQUEST_VERBOSE', '0'),
        os.environ.get('LOG_REQUEST_BODY', '0'),
        os.environ.get('LOG_REQUEST_VERBOSE_IGNORE_PATHS', ''),
        os.environ.get('LOG_RESPONSE_ERROR_BODY', '0'),
    )
    
    @app.before_request
    def before_request_logging():
        """Log información detallada de cada request"""
        # Solo loguear rutas importantes (no static files)
        if request.path.startswith('/static/'):
            return
        if request.path == '/whatsapp/webhook' and not _is_truthy_env('LOG_WHATSAPP_WEBHOOK', '0'):
            return
        if not request.path.startswith('/static/'):
            log_request_info()
    
    @app.after_request
    def after_request_logging(response):
        """Log información de cada response"""
        if request.path.startswith('/static/'):
            return response
        if request.path == '/whatsapp/webhook' and not _is_truthy_env('LOG_WHATSAPP_WEBHOOK', '0'):
            return response
        if not request.path.startswith('/static/'):
            log_response_info(response)
        return response

    try:
        from sqlalchemy import event as sa_event

        slow_query_ms = max(1, _as_int_env('OBS_SLOW_QUERY_MS', 250))
        sql_text_max_len = max(80, _as_int_env('OBS_SQL_TEXT_MAX_LEN', 240))

        def _before_cursor_execute(_conn, _cursor, _statement, _parameters, context, _executemany):
            context._obs_query_started_at = time.perf_counter()

        def _after_cursor_execute(_conn, _cursor, statement, parameters, context, _executemany):
            started_at = getattr(context, '_obs_query_started_at', None)
            if started_at is None:
                return
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            req_id = None
            endpoint = '-'
            path = '-'
            if has_request_context():
                req_id = getattr(g, 'request_id', None)
                g.db_query_count = int(getattr(g, 'db_query_count', 0) or 0) + 1
                g.db_query_elapsed_ms = float(getattr(g, 'db_query_elapsed_ms', 0.0) or 0.0) + elapsed_ms
                endpoint = request.endpoint or '-'
                path = request.path or '-'
            if elapsed_ms < slow_query_ms:
                return
            if has_request_context():
                g.db_slow_query_count = int(getattr(g, 'db_slow_query_count', 0) or 0) + 1
            prefix = f'[{req_id}] ' if req_id else ''
            sql = ' '.join((statement or '').split())
            if len(sql) > sql_text_max_len:
                sql = f"{sql[:sql_text_max_len]}…"
            app.logger.warning(
                f"{prefix}SLOW_SQL {elapsed_ms:.1f}ms endpoint={endpoint} path={path} sql={sql} params={parameters}"
            )

        with app.app_context():
            engine = db.engine
            if not getattr(engine, '_obs_slow_sql_listener_registered', False):
                sa_event.listen(engine, "before_cursor_execute", _before_cursor_execute)
                sa_event.listen(engine, "after_cursor_execute", _after_cursor_execute)
                setattr(engine, '_obs_slow_sql_listener_registered', True)

        @sa_event.listens_for(db.session, "after_commit")
        def _after_commit(_session):
            if not _is_truthy_env('LOG_DB_COMMITS', '0'):
                return
            req_id = getattr(g, 'request_id', None)
            prefix = f'[{req_id}] ' if req_id else ''
            app.logger.info(f"{prefix}DB COMMIT")

        @sa_event.listens_for(db.session, "after_rollback")
        def _after_rollback(_session):
            req_id = getattr(g, 'request_id', None)
            prefix = f'[{req_id}] ' if req_id else ''
            app.logger.warning(f"{prefix}DB ROLLBACK")
    except Exception:
        pass
    
    # Registrar blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.productos import productos_bp
    from app.routes.servicios import servicios_bp
    from app.routes.ventas import ventas_bp
    from app.routes.caja import caja_bp
    from app.routes.compras import compras_bp
    from app.routes import compras_edicion as _compras_edicion  # noqa: F401
    from app.routes.clientes import clientes_bp
    from app.routes.clientes_servicios import clientes_servicios_bp
    from app.routes.clientes_calificacion import clientes_calificacion_bp
    from app.routes.clientes_fidelizacion import clientes_fidelizacion_bp
    from app.routes.reportes import reportes_bp
    from app.routes.reportes_tecnicos import reportes_tecnicos_bp
    from app.routes.proveedores import proveedores_bp
    from app.routes.autorizaciones import bp as autorizaciones_bp
    from app.routes.usuarios import usuarios_bp
    from app.routes.roles import roles_bp
    from app.routes.auditoria import auditoria_bp, auditoria_api_bp
    from app.routes.reparaciones import reparaciones_bp
    from app.routes.recepcion_usados import recepcion_usados_bp
    from app.routes.presupuestos_empresariales import presupuestos_empresariales_bp
    from app.routes.seguimiento import seguimiento_bp
    from app.routes.whatsapp import whatsapp_bp
    from app.routes.agenda import agenda_bp
    from app.routes.inteligencia import inteligencia_bp
    from app.routes.asistente_ia import asistente_ia_bp
    from app.routes.insights_diarios import insights_diarios_bp
    from app.routes.tienda_api import tienda_api_bp
    from app.routes.tienda_gastronomia_api import tienda_gastronomia_api_bp
    from app.routes.tienda_promociones_api import tienda_promociones_api_bp
    from app.routes.tienda_bot_api import tienda_bot_api_bp
    from app.routes.tienda_admin import tienda_admin_bp
    from app.routes.tienda_public import tienda_public_bp
    from app.routes.publicidad_ads import publicidad_ads_bp
    from gastronomia import (
        gastronomia_api_bp,
        gastronomia_bp,
        gastronomia_channel_price_api_bp,
        gastronomia_caja_api_bp,
        gastronomia_cocina_api_bp,
        gastronomia_delivery_api_bp,
        gastronomia_entregas_api_bp,
        gastronomia_menu_tv_api_bp,
        gastronomia_pedidos_api_bp,
        gastronomia_reportes_api_bp,
        gastronomia_salon_api_bp,
        gastronomia_stock_api_bp,
    )
    from pedidos import pedidos_bp, pedidos_api_bp, pedidos_caja_bp
    from cobranzas.routes_clientes import cobranzas_clientes_bp
    from cobranzas.routes_cobros import cobranzas_cobros_bp
    from cobranzas.routes_cuentas import cobranzas_cuentas_bp
    from cobranzas.routes import cobranzas_bp
    from control_de_empleados.routes import control_empleados_bp
    from gastos_corrientes.routes import gastos_corrientes_bp
    from flujo_caja.routes import flujo_caja_bp
    from facturacion_electronica.routes import facturacion_electronica_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(productos_bp, url_prefix='/productos')
    app.register_blueprint(servicios_bp, url_prefix='/servicios')
    app.register_blueprint(ventas_bp, url_prefix='/ventas')
    app.register_blueprint(caja_bp, url_prefix='/caja')
    app.register_blueprint(compras_bp, url_prefix='/compras')
    app.register_blueprint(clientes_bp, url_prefix='/clientes')
    app.register_blueprint(clientes_servicios_bp, url_prefix='/clientes')
    app.register_blueprint(clientes_calificacion_bp, url_prefix='/clientes')
    app.register_blueprint(clientes_fidelizacion_bp, url_prefix='/clientes')
    app.register_blueprint(reportes_bp, url_prefix='/reportes')
    app.register_blueprint(reportes_tecnicos_bp, url_prefix='/reportes')
    app.register_blueprint(proveedores_bp, url_prefix='/proveedores')
    app.register_blueprint(autorizaciones_bp)  # Ya tiene url_prefix='/api/autorizacion'
    app.register_blueprint(usuarios_bp, url_prefix='/usuarios')
    app.register_blueprint(roles_bp, url_prefix='/roles')
    app.register_blueprint(auditoria_bp, url_prefix='/auditoria')
    app.register_blueprint(auditoria_api_bp)
    app.register_blueprint(reparaciones_bp, url_prefix='/reparaciones')
    app.register_blueprint(recepcion_usados_bp, url_prefix='/recepcion-usados')
    app.register_blueprint(presupuestos_empresariales_bp, url_prefix='/presupuestos-empresariales')
    app.register_blueprint(seguimiento_bp, url_prefix='/seguimiento')  # Público, sin autenticación
    app.register_blueprint(whatsapp_bp, url_prefix='/whatsapp')
    app.register_blueprint(agenda_bp, url_prefix='/agenda')
    app.register_blueprint(inteligencia_bp)
    app.register_blueprint(asistente_ia_bp)
    app.register_blueprint(insights_diarios_bp)
    app.register_blueprint(tienda_api_bp, url_prefix='/api/tienda')
    app.register_blueprint(tienda_api_bp, url_prefix='/tienda/api/tienda', name='tienda_api_prefixed')
    app.register_blueprint(tienda_gastronomia_api_bp, url_prefix='/api/tienda')
    app.register_blueprint(tienda_gastronomia_api_bp, url_prefix='/tienda/api/tienda', name='tienda_gastronomia_api_prefixed')
    app.register_blueprint(tienda_promociones_api_bp, url_prefix='/api/tienda')
    app.register_blueprint(tienda_bot_api_bp, url_prefix='/api/tienda')
    app.register_blueprint(tienda_admin_bp)
    app.register_blueprint(tienda_public_bp)
    app.register_blueprint(publicidad_ads_bp)
    app.register_blueprint(gastronomia_bp, url_prefix='/gastronomia')
    app.register_blueprint(gastronomia_api_bp, url_prefix='/api/gastronomia')
    app.register_blueprint(gastronomia_channel_price_api_bp, url_prefix='/api/gastronomia')
    app.register_blueprint(gastronomia_caja_api_bp, url_prefix='/api/gastronomia')
    app.register_blueprint(gastronomia_cocina_api_bp, url_prefix='/api/gastronomia')
    app.register_blueprint(gastronomia_delivery_api_bp, url_prefix='/api/gastronomia')
    app.register_blueprint(gastronomia_entregas_api_bp, url_prefix='/api/gastronomia')
    app.register_blueprint(gastronomia_menu_tv_api_bp, url_prefix='/api/gastronomia')
    app.register_blueprint(gastronomia_pedidos_api_bp, url_prefix='/api/gastronomia')
    app.register_blueprint(gastronomia_reportes_api_bp, url_prefix='/api/gastronomia')
    app.register_blueprint(gastronomia_salon_api_bp, url_prefix='/api/gastronomia')
    app.register_blueprint(gastronomia_stock_api_bp, url_prefix='/api/gastronomia')
    app.register_blueprint(pedidos_bp, url_prefix='/pedidos')
    app.register_blueprint(pedidos_api_bp, url_prefix='/pedidos')
    app.register_blueprint(pedidos_caja_bp, url_prefix='/pedidos')
    app.register_blueprint(cobranzas_clientes_bp, url_prefix='/cobranzas')
    app.register_blueprint(cobranzas_cobros_bp, url_prefix='/cobranzas')
    app.register_blueprint(cobranzas_cuentas_bp, url_prefix='/cobranzas')
    app.register_blueprint(cobranzas_bp, url_prefix='/cobranzas')
    app.register_blueprint(control_empleados_bp, url_prefix='/control-empleados')
    app.register_blueprint(gastos_corrientes_bp, url_prefix='/gastos-corrientes')
    app.register_blueprint(flujo_caja_bp, url_prefix='/flujo-caja')
    app.register_blueprint(facturacion_electronica_bp, url_prefix='/facturacion-electronica')
    if app.config.get('CRM_ENABLED', True):
        from app.routes.crm import crm_bp
        app.register_blueprint(crm_bp, url_prefix='/crm')

    # Eximir webhook de WhatsApp de CSRF (Meta no envia token CSRF)
    csrf.exempt(whatsapp_bp)
    csrf.exempt(tienda_bot_api_bp)
    csrf.exempt(tienda_gastronomia_api_bp)
    
    initialize_database(app, db, config_name)
    from app.bootstrap.tienda_schema import ensure_tienda_config_schema
    with app.app_context():
        ensure_tienda_config_schema()
    register_runtime_features(app, db)

    return app
