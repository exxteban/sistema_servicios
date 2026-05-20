"""
Configuracion separada para el asistente IA interno.
"""
from dataclasses import dataclass

from app.models import Configuracion
from app.services.ia.settings_resolver import clean_env_value, get_setting, get_setting_bool, safe_float, safe_int


CLAVE_ENABLED = 'ia_backoffice_enabled'
CLAVE_PROVIDER = 'ia_backoffice_provider'
CLAVE_MODEL = 'ia_backoffice_model'
CLAVE_DEEPSEEK_BASE_URL = 'ia_backoffice_deepseek_base_url'
CLAVE_MAX_TOKENS = 'ia_backoffice_max_tokens'
CLAVE_TEMPERATURE = 'ia_backoffice_temperature'
CLAVE_DAILY_TOKEN_BUDGET = 'ia_backoffice_daily_token_budget'
CLAVE_MONTHLY_TOKEN_BUDGET = 'ia_backoffice_monthly_token_budget'
CLAVE_READONLY_MODE = 'ia_backoffice_readonly_mode'
CLAVE_ASSISTED_ACTIONS_ENABLED = 'ia_backoffice_assisted_actions_enabled'
CLAVE_ADVANCED_MODEL_ENABLED = 'ia_backoffice_advanced_model_enabled'
CLAVE_ADVANCED_MODEL = 'ia_backoffice_advanced_model'
CLAVE_SYSTEM_ROOT_USER_ID = 'system_root_user_id'


IA_BACKOFFICE_DEFAULTS = {
    CLAVE_ENABLED: ('0', 'Habilita el asistente IA interno del backoffice'),
    CLAVE_PROVIDER: ('deepseek', 'Proveedor IA del asistente interno'),
    CLAVE_MODEL: ('deepseek-v4-flash', 'Modelo rapido del asistente interno'),
    CLAVE_DEEPSEEK_BASE_URL: ('https://api.deepseek.com', 'Base URL DeepSeek del asistente interno'),
    CLAVE_MAX_TOKENS: ('700', 'Maximo de tokens por respuesta del asistente interno'),
    CLAVE_TEMPERATURE: ('0.3', 'Temperatura del asistente interno'),
    CLAVE_DAILY_TOKEN_BUDGET: ('50000', 'Presupuesto diario de tokens del asistente interno'),
    CLAVE_MONTHLY_TOKEN_BUDGET: ('1000000', 'Presupuesto mensual de tokens del asistente interno'),
    CLAVE_READONLY_MODE: ('1', 'Modo solo lectura del asistente interno'),
    CLAVE_ASSISTED_ACTIONS_ENABLED: ('0', 'Habilita acciones asistidas confirmables del asistente interno'),
    CLAVE_ADVANCED_MODEL_ENABLED: ('0', 'Permite modelo avanzado del asistente interno'),
    CLAVE_ADVANCED_MODEL: ('deepseek-v4-pro', 'Modelo avanzado del asistente interno'),
    CLAVE_SYSTEM_ROOT_USER_ID: ('', 'Usuario root exacto habilitado para switches globales'),
}


@dataclass(frozen=True)
class ConfiguracionAsistenteIA:
    enabled: bool
    provider: str
    model: str
    deepseek_base_url: str
    max_tokens: int
    temperature: float
    daily_token_budget: int
    monthly_token_budget: int
    readonly_mode: bool
    assisted_actions_enabled: bool
    advanced_model_enabled: bool
    advanced_model: str


def asegurar_defaults_asistente() -> None:
    for clave, (valor, descripcion) in IA_BACKOFFICE_DEFAULTS.items():
        if Configuracion.obtener(clave, None) is None:
            Configuracion.establecer(clave, valor, descripcion)


def normalizar_provider(provider: str | None) -> str:
    provider_norm = clean_env_value(provider).lower()
    if provider_norm not in {'openai', 'deepseek'}:
        return 'deepseek'
    return provider_norm


def normalizar_modelo_backoffice(provider: str, model: str | None) -> str:
    provider_norm = normalizar_provider(provider)
    model_norm = clean_env_value(model)
    if provider_norm == 'deepseek':
        if not model_norm or model_norm.startswith('gpt-') or model_norm.startswith('o'):
            return 'deepseek-v4-flash'
        return model_norm
    if not model_norm or model_norm.startswith('deepseek'):
        return 'gpt-4o-mini'
    return model_norm


def obtener_configuracion_asistente() -> ConfiguracionAsistenteIA:
    enabled, _raw_enabled, _src_enabled = get_setting_bool(CLAVE_ENABLED, 'AI_BACKOFFICE_ENABLED', default=False)
    readonly, _raw_readonly, _src_readonly = get_setting_bool(CLAVE_READONLY_MODE, 'AI_BACKOFFICE_READONLY_MODE', default=True)
    assisted_actions, _raw_actions, _src_actions = get_setting_bool(
        CLAVE_ASSISTED_ACTIONS_ENABLED,
        'AI_BACKOFFICE_ASSISTED_ACTIONS_ENABLED',
        default=False,
    )
    advanced, _raw_advanced, _src_advanced = get_setting_bool(
        CLAVE_ADVANCED_MODEL_ENABLED,
        'AI_BACKOFFICE_ADVANCED_MODEL_ENABLED',
        default=False,
    )

    provider_raw, _ = get_setting(CLAVE_PROVIDER, 'AI_BACKOFFICE_PROVIDER', default='deepseek', clean=True)
    provider = normalizar_provider(provider_raw)
    model_raw, _ = get_setting(CLAVE_MODEL, 'AI_BACKOFFICE_MODEL', default='deepseek-v4-flash', clean=True)
    advanced_model_raw, _ = get_setting(CLAVE_ADVANCED_MODEL, 'AI_BACKOFFICE_ADVANCED_MODEL', default='deepseek-v4-pro', clean=True)
    base_url, _ = get_setting(
        CLAVE_DEEPSEEK_BASE_URL,
        'AI_BACKOFFICE_DEEPSEEK_BASE_URL',
        default='https://api.deepseek.com',
        clean=True,
    )
    max_tokens_raw, _ = get_setting(CLAVE_MAX_TOKENS, 'AI_BACKOFFICE_MAX_TOKENS', default='700')
    temperature_raw, _ = get_setting(CLAVE_TEMPERATURE, 'AI_BACKOFFICE_TEMPERATURE', default='0.3')
    daily_budget_raw, _ = get_setting(CLAVE_DAILY_TOKEN_BUDGET, 'AI_BACKOFFICE_DAILY_TOKEN_BUDGET', default='50000')
    monthly_budget_raw, _ = get_setting(CLAVE_MONTHLY_TOKEN_BUDGET, 'AI_BACKOFFICE_MONTHLY_TOKEN_BUDGET', default='1000000')

    return ConfiguracionAsistenteIA(
        enabled=enabled,
        provider=provider,
        model=normalizar_modelo_backoffice(provider, model_raw),
        deepseek_base_url=(base_url or 'https://api.deepseek.com').rstrip('/'),
        max_tokens=max(80, min(safe_int(max_tokens_raw, 700), 4000)),
        temperature=max(0.0, min(safe_float(temperature_raw, 0.3), 1.0)),
        daily_token_budget=max(0, safe_int(daily_budget_raw, 50000)),
        monthly_token_budget=max(0, safe_int(monthly_budget_raw, 1000000)),
        readonly_mode=readonly,
        assisted_actions_enabled=assisted_actions,
        advanced_model_enabled=advanced,
        advanced_model=normalizar_modelo_backoffice(provider, advanced_model_raw),
    )
