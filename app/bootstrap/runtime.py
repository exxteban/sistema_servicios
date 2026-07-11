import os
import threading
import time

from flask import g, request, url_for
from flask_login import current_user

from app.utils.bi_context import register_bi_context


_wa_scheduler_lock = threading.Lock()
_wa_scheduler_started = False


def _is_truthy_env(name: str, default: str = '0') -> bool:
    raw = os.environ.get(name, default)
    return (raw or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on', 'si', 'sí'}


def _permissions_policy_value() -> str:
    """Permissions-Policy del sitio.

    La geolocalizacion debe permitirse en el propio origen para que el GPS del
    delivery funcione (sin allowlist el navegador bloquea la API y nunca pide
    permiso al usuario). Se puede sobreescribir con la variable de entorno
    PERMISSIONS_POLICY si una instancia necesita un valor distinto.
    """
    override = (os.environ.get('PERMISSIONS_POLICY') or '').strip()
    if override:
        return override
    return 'geolocation=(self), microphone=(), camera=()'


def register_runtime_features(app, db):
    from app.utils.helpers import (
        now_local, local_strftime, normalize_for_thermal_printer, get_app_timezone_name,
        config_moneda, formato_moneda_local,
    )
    from app.services.brand_logos import resolve_electronics_brand_logo

    app.jinja_env.globals['now'] = now_local
    app.jinja_env.globals['app_timezone_name'] = get_app_timezone_name
    app.jinja_env.globals['resolve_electronics_brand_logo'] = resolve_electronics_brand_logo
    app.jinja_env.globals['app_moneda_config'] = config_moneda
    app.jinja_env.filters['local_strftime'] = local_strftime
    app.jinja_env.filters['thermal_safe'] = normalize_for_thermal_printer
    app.jinja_env.filters['moneda'] = formato_moneda_local

    def static_url(filename: str):
        try:
            file_path = os.path.join(app.static_folder, filename)
            version = int(os.path.getmtime(file_path))
            return url_for('static', filename=filename, v=version)
        except Exception:
            return url_for('static', filename=filename)

    app.jinja_env.globals['static_url'] = static_url
    register_bi_context(app)

    config_ui_keys = (
        'nombre_empresa_ui',
        'nombre_empresa',
        'logo_empresa_ui_path',
        'control_empleados_activo',
        'servicio_tecnico_activo',
        'ventas_credito_activo',
        'whatsapp_activo',
        'crm_activo',
        'cobranzas_activo',
        'flujo_caja_activo',
        'facturacion_electronica_activo',
        'ia_provider',
        'ia_model',
        'ia_max_tokens',
        'ia_temperature',
        'ia_enabled',
        'ia_base_url',
        'ia_deepseek_base_url',
        'ia_openai_api_key',
        'ia_deepseek_api_key',
        'ia_api_key',
    )

    def _obtener_configuracion_ui_mapa():
        cached = getattr(g, '_runtime_ui_config', None)
        if cached is not None:
            return cached
        valores = {}
        try:
            from app.models import Configuracion

            filas = (
                Configuracion.query
                .filter(Configuracion.clave.in_(config_ui_keys))
                .all()
            )
            valores = {fila.clave: fila.valor for fila in filas}
        except Exception:
            valores = {}
        g._runtime_ui_config = valores
        return valores

    @app.context_processor
    def inject_branding():
        nombre_empresa = ''
        logo_empresa_path = ''
        modulo_control_empleados_activo = False
        modulo_servicio_tecnico_activo = True
        ventas_credito_activo = False
        modulo_whatsapp_activo = True
        modulo_crm_activo = bool(app.config.get('CRM_ENABLED', True))
        modulo_cobranzas_activo = False
        modulo_flujo_caja_activo = True
        modulo_facturacion_electronica_activo = False
        es_usuario_root_actual = False
        try:
            from control_de_empleados import CLAVE_MODULO_CONTROL_EMPLEADOS
            from cobranzas import CLAVE_COBRANZAS_ACTIVO, CLAVE_VENTAS_CREDITO_ACTIVO
            from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO
            from app.models import Configuracion
            from app.services.ia_backoffice.security import es_usuario_root
            from app.services.system_modules import (
                CLAVE_MODULO_CRM,
                CLAVE_MODULO_SERVICIO_TECNICO,
                CLAVE_MODULO_WHATSAPP,
                get_system_module,
            )
            from flujo_caja import CLAVE_MODULO_FLUJO_CAJA

            configuraciones = _obtener_configuracion_ui_mapa()
            nombre_empresa = (configuraciones.get('nombre_empresa_ui', '') or '').strip()
            if not nombre_empresa:
                nombre_empresa = (configuraciones.get('nombre_empresa', '') or '').strip()
            logo_empresa_path = (configuraciones.get('logo_empresa_ui_path', '') or '').strip()
            modulo_control_empleados_activo = Configuracion.parse_bool(
                configuraciones.get(CLAVE_MODULO_CONTROL_EMPLEADOS),
                default=bool((get_system_module(CLAVE_MODULO_CONTROL_EMPLEADOS) or {}).get('default', False)),
            )
            modulo_servicio_tecnico_activo = Configuracion.parse_bool(
                configuraciones.get(CLAVE_MODULO_SERVICIO_TECNICO),
                default=bool((get_system_module(CLAVE_MODULO_SERVICIO_TECNICO) or {}).get('default', True)),
            )
            ventas_credito_activo = Configuracion.parse_bool(
                configuraciones.get(CLAVE_VENTAS_CREDITO_ACTIVO),
                default=bool((get_system_module(CLAVE_VENTAS_CREDITO_ACTIVO) or {}).get('default', False)),
            )
            modulo_whatsapp_activo = Configuracion.parse_bool(
                configuraciones.get(CLAVE_MODULO_WHATSAPP),
                default=bool((get_system_module(CLAVE_MODULO_WHATSAPP) or {}).get('default', True)),
            )
            modulo_crm_activo = bool(app.config.get('CRM_ENABLED', True)) and Configuracion.parse_bool(
                configuraciones.get(CLAVE_MODULO_CRM),
                default=bool((get_system_module(CLAVE_MODULO_CRM) or {}).get('default', True)),
            )
            modulo_cobranzas_activo = Configuracion.parse_bool(
                configuraciones.get(CLAVE_COBRANZAS_ACTIVO),
                default=bool((get_system_module(CLAVE_COBRANZAS_ACTIVO) or {}).get('default', False)),
            )
            modulo_flujo_caja_activo = Configuracion.parse_bool(
                configuraciones.get(CLAVE_MODULO_FLUJO_CAJA),
                default=bool((get_system_module(CLAVE_MODULO_FLUJO_CAJA) or {}).get('default', True)),
            )
            modulo_facturacion_electronica_activo = Configuracion.parse_bool(
                configuraciones.get(CLAVE_FACTURACION_ELECTRONICA_ACTIVO),
                default=bool((get_system_module(CLAVE_FACTURACION_ELECTRONICA_ACTIVO) or {}).get('default', False)),
            )
            es_usuario_root_actual = es_usuario_root(current_user)
        except Exception:
            nombre_empresa = ''
            logo_empresa_path = ''
            modulo_control_empleados_activo = False
            modulo_servicio_tecnico_activo = True
            ventas_credito_activo = False
            modulo_whatsapp_activo = True
            modulo_crm_activo = bool(app.config.get('CRM_ENABLED', True))
            modulo_cobranzas_activo = False
            modulo_flujo_caja_activo = True
            modulo_facturacion_electronica_activo = False
            es_usuario_root_actual = False
        return {
            'app_brand_name': nombre_empresa,
            'app_brand_logo_path': logo_empresa_path,
            'modulo_control_empleados_activo': modulo_control_empleados_activo,
            'modulo_servicio_tecnico_activo': modulo_servicio_tecnico_activo,
            'ventas_credito_activo': ventas_credito_activo,
            'modulo_whatsapp_activo': modulo_whatsapp_activo,
            'modulo_crm_activo': modulo_crm_activo,
            'modulo_cobranzas_activo': modulo_cobranzas_activo,
            'modulo_flujo_caja_activo': modulo_flujo_caja_activo,
            'modulo_facturacion_electronica_activo': modulo_facturacion_electronica_activo,
            'es_usuario_root_actual': es_usuario_root_actual,
        }

    @app.context_processor
    def inject_ai_settings():
        provider = (os.environ.get('AI_PROVIDER', 'openai') or '').strip().lower() or 'openai'
        model = (os.environ.get('AI_MODEL', 'gpt-4o-mini') or '').strip() or 'gpt-4o-mini'
        max_tokens = (os.environ.get('AI_MAX_TOKENS', '320') or '').strip() or '320'
        temperature = (os.environ.get('AI_TEMPERATURE', '0.7') or '').strip() or '0.7'
        enabled = (os.environ.get('AI_ENABLED', '0') or '').strip().lower() in ('1', 'true', 'yes', 'si', 'sí', 'on')
        ia_base_url = (os.environ.get('AI_BASE_URL', '') or '').strip()
        deepseek_base_url = (os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1') or '').strip()
        openai_key_configurada = bool((os.environ.get('OPENAI_API_KEY', '') or '').strip())
        deepseek_key_configurada = bool((os.environ.get('DEEPSEEK_API_KEY', '') or '').strip())
        generic_key_configurada = bool((os.environ.get('AI_API_KEY', '') or '').strip())
        try:
            from app.models import Configuracion

            configuraciones = _obtener_configuracion_ui_mapa()
            provider = (configuraciones.get('ia_provider', provider) or provider).strip().lower() or provider
            model = (configuraciones.get('ia_model', model) or model).strip() or model
            max_tokens = (configuraciones.get('ia_max_tokens', max_tokens) or max_tokens).strip() or max_tokens
            temperature = (configuraciones.get('ia_temperature', temperature) or temperature).strip() or temperature
            enabled = Configuracion.parse_bool(
                configuraciones.get('ia_enabled', '1' if enabled else '0'),
                default=enabled,
            )
            ia_base_url = (configuraciones.get('ia_base_url', ia_base_url) or ia_base_url).strip()
            deepseek_base_url = (configuraciones.get('ia_deepseek_base_url', deepseek_base_url) or deepseek_base_url).strip()
            openai_key_configurada = bool((configuraciones.get('ia_openai_api_key', '') or '').strip()) or openai_key_configurada
            deepseek_key_configurada = bool((configuraciones.get('ia_deepseek_api_key', '') or '').strip()) or deepseek_key_configurada
            generic_key_configurada = bool((configuraciones.get('ia_api_key', '') or '').strip()) or generic_key_configurada
        except Exception:
            pass
        if provider not in ('openai', 'deepseek'):
            provider = 'openai'
        return {
            'ia_enabled_ui': enabled,
            'ia_provider_ui': provider,
            'ia_model_ui': model,
            'ia_max_tokens_ui': max_tokens,
            'ia_temperature_ui': temperature,
            'ia_base_url_ui': ia_base_url,
            'ia_deepseek_base_url_ui': deepseek_base_url,
            'ia_openai_key_configurada_ui': openai_key_configurada,
            'ia_deepseek_key_configurada_ui': deepseek_key_configurada,
            'ia_generic_key_configurada_ui': generic_key_configurada,
        }

    @app.after_request
    def add_header(response):
        if request.path.startswith('/static/'):
            if request.path.startswith('/static/tienda_dist/assets/'):
                response.cache_control.max_age = 31536000
                response.cache_control.public = True
                try:
                    response.headers['Cache-Control'] = f"{response.headers.get('Cache-Control', '')}, immutable".strip(', ')
                except Exception:
                    pass
            elif request.args.get('v'):
                response.cache_control.max_age = 31536000
                response.cache_control.public = True
                try:
                    response.headers['Cache-Control'] = f"{response.headers.get('Cache-Control', '')}, immutable".strip(', ')
                except Exception:
                    pass
            else:
                response.cache_control.no_cache = True
                response.cache_control.max_age = 0
                response.cache_control.must_revalidate = True
                response.headers['Pragma'] = 'no-cache'
        if _is_truthy_env('SECURITY_HEADERS_ENABLED', '1'):
            response.headers.setdefault('X-Content-Type-Options', 'nosniff')
            response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
            response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
            response.headers.setdefault('Permissions-Policy', _permissions_policy_value())
        if _is_truthy_env('HSTS_ENABLED', '0') and request.is_secure:
            max_age_raw = (os.environ.get('HSTS_MAX_AGE') or '31536000').strip()
            try:
                max_age = max(0, int(max_age_raw))
            except Exception:
                max_age = 31536000
            hsts_value = f'max-age={max_age}'
            if _is_truthy_env('HSTS_INCLUDE_SUBDOMAINS', '1'):
                hsts_value = f'{hsts_value}; includeSubDomains'
            if _is_truthy_env('HSTS_PRELOAD', '0'):
                hsts_value = f'{hsts_value}; preload'
            response.headers.setdefault('Strict-Transport-Security', hsts_value)
        return response

    try:
        from app.services.whatsapp import asignacion_service as whatsapp_assignment_service

        if not getattr(whatsapp_assignment_service, '_runtime_patch_multi_asesor', False):
            def _aplicar_accion_timeout_parche(asignacion, accion, motivo, ahora):
                estado_anterior = db.session.get(whatsapp_assignment_service.WhatsAppEstadoAsesor, asignacion.id_asesor)
                if estado_anterior and (estado_anterior.conversaciones_activas or 0) > 0:
                    estado_anterior.conversaciones_activas -= 1

                asignacion.estado = 'devuelta'
                asignacion.cerrado_at = ahora
                asignacion.motivo_devolucion = motivo

                nuevo_asesor = None
                if accion == 'reasignar':
                    asesores = whatsapp_assignment_service._asesores_disponibles(whatsapp_assignment_service._get_distribucion_config())
                    for candidato in asesores:
                        if candidato.id_usuario != asignacion.id_asesor:
                            nuevo_asesor = candidato
                            break

                if nuevo_asesor and asignacion.conversacion:
                    whatsapp_assignment_service._asignar_conversacion_a_asesor(asignacion.conversacion, nuevo_asesor, estado='pendiente', ahora=ahora)
                    app.logger.info(
                        f"[timeout] Conv {asignacion.id_conversacion} ({motivo}): "
                        f"reasignada de asesor {asignacion.id_asesor} → asesor {nuevo_asesor.id_usuario}"
                    )
                else:
                    if asignacion.conversacion:
                        asignacion.conversacion.modo = 'derivacion'
                    app.logger.info(
                        f"[timeout] Conv {asignacion.id_conversacion} ({motivo}): enviada a cola general"
                    )
                return True

            whatsapp_assignment_service._aplicar_accion_timeout = _aplicar_accion_timeout_parche
            whatsapp_assignment_service._runtime_patch_multi_asesor = True
    except Exception:
        app.logger.exception('No se pudo aplicar parche runtime de reasignación WhatsApp')

    global _wa_scheduler_started
    scheduler_enabled = _is_truthy_env('WHATSAPP_TIMEOUT_SCHEDULER', '1')
    if scheduler_enabled and not app.config.get('TESTING', False):
        is_reloader_child = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
        should_start = (not app.debug) or is_reloader_child
        if should_start:
            with _wa_scheduler_lock:
                if not _wa_scheduler_started:
                    try:
                        interval_raw = os.environ.get('WHATSAPP_TIMEOUT_INTERVAL_SECONDS', '30')
                        interval = max(5, int(interval_raw))
                    except Exception:
                        interval = 30

                    def _wa_timeout_loop():
                        while True:
                            try:
                                with app.app_context():
                                    from app.services.whatsapp.asignacion_service import verificar_timeouts

                                    verificar_timeouts()
                            except Exception:
                                app.logger.exception('Error en scheduler de timeouts WhatsApp')
                            time.sleep(interval)

                    worker = threading.Thread(
                        target=_wa_timeout_loop,
                        name='wa-timeout-scheduler',
                        daemon=True,
                    )
                    worker.start()
                    _wa_scheduler_started = True
                    app.logger.info(f"Scheduler timeouts WhatsApp iniciado cada {interval}s")
