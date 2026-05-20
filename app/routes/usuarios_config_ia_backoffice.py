from flask import flash, jsonify, redirect, request, url_for
from flask_login import current_user, login_required

from app.models import Configuracion
from app.routes.usuarios import usuarios_bp
from app.services.ia_backoffice.security import puede_gestionar_asistente_ia
from app.services.ia_backoffice.settings import (
    CLAVE_ADVANCED_MODEL_ENABLED,
    CLAVE_ADVANCED_MODEL,
    CLAVE_ASSISTED_ACTIONS_ENABLED,
    CLAVE_DAILY_TOKEN_BUDGET,
    CLAVE_DEEPSEEK_BASE_URL,
    CLAVE_ENABLED,
    CLAVE_MAX_TOKENS,
    CLAVE_MODEL,
    CLAVE_MONTHLY_TOKEN_BUDGET,
    CLAVE_PROVIDER,
    CLAVE_READONLY_MODE,
    CLAVE_TEMPERATURE,
    asegurar_defaults_asistente,
    normalizar_modelo_backoffice,
    normalizar_provider,
)


def _quiere_json() -> bool:
    return bool(request.is_json or 'application/json' in (request.headers.get('Accept') or ''))


def _payload() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    return {key: values[-1] for key, values in request.form.lists() if values}


def _bool_payload(data: dict, key: str, default: bool = False) -> bool:
    if key not in data:
        return default
    return Configuracion.parse_bool(data.get(key), default=default)


def _int_payload(data: dict, key: str, default: int, minimo: int, maximo: int) -> int:
    try:
        value = int(str(data.get(key, default)).strip())
    except Exception:
        value = default
    return max(minimo, min(value, maximo))


def _float_payload(data: dict, key: str, default: float, minimo: float, maximo: float) -> float:
    try:
        value = float(str(data.get(key, default)).strip().replace(',', '.'))
    except Exception:
        value = default
    return max(minimo, min(value, maximo))


@usuarios_bp.route('/configuracion/ia-backoffice', methods=['POST'])
@login_required
def configuracion_ia_backoffice():
    if not puede_gestionar_asistente_ia(current_user):
        if _quiere_json():
            return jsonify({'error': 'sin_permisos', 'mensaje': 'Solo el usuario root puede gestionar la IA interna.'}), 403
        flash('Solo el usuario root puede gestionar la IA interna.', 'danger')
        return redirect(url_for('usuarios.configuracion'))

    asegurar_defaults_asistente()
    data = _payload()
    provider = normalizar_provider(data.get('ia_backoffice_provider', 'deepseek'))
    model = normalizar_modelo_backoffice(provider, data.get('ia_backoffice_model', 'deepseek-v4-flash'))
    base_url = (data.get('ia_backoffice_deepseek_base_url') or 'https://api.deepseek.com').strip().rstrip('/')

    Configuracion.establecer_bool(CLAVE_ENABLED, _bool_payload(data, 'ia_backoffice_enabled'), 'Habilita IA interna')
    Configuracion.establecer(CLAVE_PROVIDER, provider, 'Proveedor IA interna')
    Configuracion.establecer(CLAVE_MODEL, model, 'Modelo IA interna')
    Configuracion.establecer(CLAVE_DEEPSEEK_BASE_URL, base_url or 'https://api.deepseek.com', 'Base URL DeepSeek IA interna')
    Configuracion.establecer(CLAVE_MAX_TOKENS, str(_int_payload(data, 'ia_backoffice_max_tokens', 700, 80, 4000)), 'Max tokens IA interna')
    Configuracion.establecer(CLAVE_TEMPERATURE, str(_float_payload(data, 'ia_backoffice_temperature', 0.3, 0.0, 1.0)), 'Temperatura IA interna')
    Configuracion.establecer(CLAVE_DAILY_TOKEN_BUDGET, str(_int_payload(data, 'ia_backoffice_daily_token_budget', 50000, 0, 10000000)), 'Budget diario IA interna')
    Configuracion.establecer(CLAVE_MONTHLY_TOKEN_BUDGET, str(_int_payload(data, 'ia_backoffice_monthly_token_budget', 1000000, 0, 100000000)), 'Budget mensual IA interna')
    Configuracion.establecer_bool(CLAVE_READONLY_MODE, _bool_payload(data, 'ia_backoffice_readonly_mode', True), 'Modo solo lectura IA interna')
    Configuracion.establecer_bool(CLAVE_ASSISTED_ACTIONS_ENABLED, _bool_payload(data, 'ia_backoffice_assisted_actions_enabled'), 'Acciones asistidas IA interna')
    Configuracion.establecer_bool(CLAVE_ADVANCED_MODEL_ENABLED, _bool_payload(data, 'ia_backoffice_advanced_model_enabled'), 'Modelo avanzado IA interna')
    advanced_model_raw = (
        data.get('ia_backoffice_advanced_model')
        or Configuracion.obtener(CLAVE_ADVANCED_MODEL, '')
        or 'deepseek-v4-pro'
    )
    Configuracion.establecer(
        CLAVE_ADVANCED_MODEL,
        normalizar_modelo_backoffice(provider, advanced_model_raw),
        'Modelo avanzado IA interna',
    )

    if _quiere_json():
        return jsonify({'ok': True, 'provider': provider, 'model': model})
    flash('Configuracion del asistente IA interno actualizada.', 'success')
    return redirect(url_for('usuarios.configuracion'))
