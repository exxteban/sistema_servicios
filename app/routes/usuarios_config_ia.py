from flask import flash, redirect, request, url_for
from flask_login import current_user, login_required
from openai import OpenAI

from app.models import Configuracion
from app.routes.usuarios import usuarios_bp
from app.services.ia.settings_resolver import clean_env_value, get_setting, normalize_model_for_provider, safe_int

CLAVE_IA_ENABLED = 'ia_enabled'
CLAVE_IA_PROVIDER = 'ia_provider'
CLAVE_IA_MODEL = 'ia_model'
CLAVE_IA_MAX_TOKENS = 'ia_max_tokens'
CLAVE_IA_TEMPERATURE = 'ia_temperature'
CLAVE_IA_API_KEY = 'ia_api_key'
CLAVE_IA_OPENAI_API_KEY = 'ia_openai_api_key'
CLAVE_IA_DEEPSEEK_API_KEY = 'ia_deepseek_api_key'
CLAVE_IA_BASE_URL = 'ia_base_url'
CLAVE_IA_DEEPSEEK_BASE_URL = 'ia_deepseek_base_url'


def _valor_desde_form_o_config(form_key: str, setting_key: str, env_key: str, default: str = '', clean: bool = False) -> str:
    valor_form = request.form.get(form_key, None)
    if valor_form is not None and str(valor_form).strip():
        return clean_env_value(valor_form) if clean else str(valor_form).strip()
    valor, _source = get_setting(setting_key, env_key, default=default, clean=clean)
    return valor


def _checkbox_bool(form_key: str, default: bool = False) -> bool:
    valores = [str(v).strip() for v in request.form.getlist(form_key) if str(v).strip()]
    if not valores:
        return default
    return Configuracion.parse_bool(valores[-1], default=default)


def _resolver_parametros_ia() -> dict:
    provider = _valor_desde_form_o_config('ia_provider', CLAVE_IA_PROVIDER, 'AI_PROVIDER', default='deepseek', clean=True).lower()
    if provider not in ('openai', 'deepseek'):
        provider = 'deepseek'

    model_raw = _valor_desde_form_o_config('ia_model', CLAVE_IA_MODEL, 'AI_MODEL', default='')
    model = normalize_model_for_provider(provider, model_raw)
    max_tokens_raw = _valor_desde_form_o_config('ia_max_tokens', CLAVE_IA_MAX_TOKENS, 'AI_MAX_TOKENS', default='80')
    max_tokens = max(20, safe_int(max_tokens_raw, 80))

    generic_key = _valor_desde_form_o_config('ia_api_key', CLAVE_IA_API_KEY, 'AI_API_KEY', clean=True)
    openai_key = _valor_desde_form_o_config('ia_openai_api_key', CLAVE_IA_OPENAI_API_KEY, 'OPENAI_API_KEY', clean=True)
    deepseek_key = _valor_desde_form_o_config('ia_deepseek_api_key', CLAVE_IA_DEEPSEEK_API_KEY, 'DEEPSEEK_API_KEY', clean=True)
    generic_base_url = _valor_desde_form_o_config('ia_base_url', CLAVE_IA_BASE_URL, 'AI_BASE_URL', clean=True)
    deepseek_base_url = _valor_desde_form_o_config(
        'ia_deepseek_base_url',
        CLAVE_IA_DEEPSEEK_BASE_URL,
        'DEEPSEEK_BASE_URL',
        default='https://api.deepseek.com/v1',
        clean=True,
    )

    api_key = ''
    base_url = ''
    if provider == 'deepseek':
        api_key = deepseek_key or generic_key or openai_key
        base_url = deepseek_base_url or generic_base_url or 'https://api.deepseek.com/v1'
    else:
        api_key = openai_key or generic_key or deepseek_key
        base_url = generic_base_url or ''

    return {
        'provider': provider,
        'model': model or 'gpt-4o-mini',
        'max_tokens': max_tokens,
        'api_key': api_key,
        'base_url': (base_url or '').rstrip('/'),
    }


@usuarios_bp.route('/configuracion/ia', methods=['POST'])
@login_required
def configuracion_ia():
    if not current_user.tiene_permiso('gestionar_usuarios'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para gestionar usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    ia_enabled = _checkbox_bool('ia_enabled', default=False)
    ia_provider = (request.form.get('ia_provider') or 'deepseek').strip().lower()
    if ia_provider not in ('openai', 'deepseek'):
        ia_provider = 'deepseek'

    ia_model = normalize_model_for_provider(ia_provider, request.form.get('ia_model'))
    ia_base_url = (request.form.get('ia_base_url') or '').strip()
    ia_deepseek_base_url = (request.form.get('ia_deepseek_base_url') or '').strip()

    max_tokens_raw = (request.form.get('ia_max_tokens') or '').strip()
    try:
        ia_max_tokens = max(1, int(max_tokens_raw or '320'))
    except Exception:
        ia_max_tokens = 320

    temperature_raw = (request.form.get('ia_temperature') or '').strip().replace(',', '.')
    try:
        ia_temperature = float(temperature_raw or '0.7')
    except Exception:
        ia_temperature = 0.7
    ia_temperature = min(2.0, max(0.0, ia_temperature))

    openai_api_key = (request.form.get('ia_openai_api_key') or '').strip()
    deepseek_api_key = (request.form.get('ia_deepseek_api_key') or '').strip()
    generic_api_key = (request.form.get('ia_api_key') or '').strip()

    Configuracion.establecer_bool(CLAVE_IA_ENABLED, ia_enabled, 'Habilita IA para respuestas automáticas')
    Configuracion.establecer(CLAVE_IA_PROVIDER, ia_provider, 'Proveedor IA principal')
    Configuracion.establecer(CLAVE_IA_MODEL, ia_model, 'Modelo IA principal')
    Configuracion.establecer(CLAVE_IA_MAX_TOKENS, str(ia_max_tokens), 'Máximo de tokens IA')
    Configuracion.establecer(CLAVE_IA_TEMPERATURE, str(ia_temperature), 'Temperatura IA')
    Configuracion.establecer(CLAVE_IA_BASE_URL, ia_base_url, 'Base URL IA genérica')
    Configuracion.establecer(CLAVE_IA_DEEPSEEK_BASE_URL, ia_deepseek_base_url, 'Base URL específica DeepSeek')

    if generic_api_key:
        Configuracion.establecer(CLAVE_IA_API_KEY, generic_api_key, 'API key IA genérica')
    elif Configuracion.parse_bool(request.form.get('ia_clear_api_key'), default=False):
        Configuracion.establecer(CLAVE_IA_API_KEY, '', 'API key IA genérica')

    if openai_api_key:
        Configuracion.establecer(CLAVE_IA_OPENAI_API_KEY, openai_api_key, 'API key OpenAI')
    elif Configuracion.parse_bool(request.form.get('ia_clear_openai_api_key'), default=False):
        Configuracion.establecer(CLAVE_IA_OPENAI_API_KEY, '', 'API key OpenAI')

    if deepseek_api_key:
        Configuracion.establecer(CLAVE_IA_DEEPSEEK_API_KEY, deepseek_api_key, 'API key DeepSeek')
    elif Configuracion.parse_bool(request.form.get('ia_clear_deepseek_api_key'), default=False):
        Configuracion.establecer(CLAVE_IA_DEEPSEEK_API_KEY, '', 'API key DeepSeek')

    flash('Configuración de IA actualizada correctamente.', 'success')
    return redirect(url_for('usuarios.configuracion'))


@usuarios_bp.route('/configuracion/ia/test', methods=['POST'])
@login_required
def configuracion_ia_test():
    if not current_user.tiene_permiso('gestionar_usuarios'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para gestionar usuarios.', 'danger')
        return redirect(url_for('main.dashboard'))

    params = _resolver_parametros_ia()
    provider = params['provider']
    model = params['model']
    max_tokens = params['max_tokens']
    api_key = params['api_key']
    base_url = params['base_url']

    if not api_key:
        flash('No hay API key configurada para probar la conexión IA.', 'warning')
        return redirect(url_for('usuarios.configuracion'))

    try:
        client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        kwargs = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': 'Respondé muy breve.'},
                {'role': 'user', 'content': 'Decí OK'},
            ],
        }
        if model.startswith('o') or model.startswith('gpt-5'):
            kwargs['max_completion_tokens'] = max_tokens
        else:
            kwargs['max_tokens'] = max_tokens
            kwargs['temperature'] = 0
        response = client.chat.completions.create(**kwargs)
        text = ((response.choices or [{}])[0].message.content or '').strip()
        if text:
            flash(f'Conexión IA OK ({provider}/{model}).', 'success')
        else:
            flash(f'Conexión IA establecida ({provider}/{model}), pero sin texto de respuesta.', 'warning')
    except Exception as e:
        flash(f'Falló la prueba de conexión IA ({provider}/{model}): {type(e).__name__}: {e}', 'danger')
    return redirect(url_for('usuarios.configuracion'))
