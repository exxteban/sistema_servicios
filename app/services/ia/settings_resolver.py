import os
from flask import has_app_context


def clean_env_value(value: str | None) -> str:
    v = (value or '').strip()
    if not v:
        return ''
    while len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'", '`'):
        v = v[1:-1].strip()
    v = v.replace('`', '').strip()
    v = ''.join(v.split())
    while v.endswith(','):
        v = v[:-1]
    return v


def get_setting(setting_key: str, env_key: str, default: str = '', clean: bool = False) -> tuple[str, str]:
    db_value = ''
    if has_app_context():
        try:
            from app.models import Configuracion
            db_value = (Configuracion.obtener(setting_key, '') or '').strip()
        except Exception:
            db_value = ''
    if db_value:
        return (clean_env_value(db_value) if clean else db_value), f'db:{setting_key}'
    env_value = os.environ.get(env_key, default)
    value = clean_env_value(env_value) if clean else (env_value or '').strip()
    if value:
        return value, env_key
    if default:
        return default, 'default'
    return '', 'missing'


def get_setting_bool(setting_key: str, env_key: str, default: bool = False) -> tuple[bool, str, str]:
    env_raw = (os.environ.get(env_key, '1' if default else '0') or '').strip()
    env_bool = env_raw.lower() in ('1', 'true', 'yes', 'si', 'sí', 'on')
    if has_app_context():
        try:
            from app.models import Configuracion
            raw_db = Configuracion.obtener(setting_key, None)
            if raw_db is not None:
                raw_db_str = str(raw_db).strip()
                parsed = Configuracion.parse_bool(raw_db_str, default=env_bool)
                return parsed, raw_db_str, f'db:{setting_key}'
        except Exception:
            pass
    return env_bool, env_raw, env_key


def safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value: str, default: float) -> float:
    try:
        return float(value.replace(',', '.'))
    except Exception:
        return default


def compact_prompt_context(value, *, depth: int = 0):
    if value is None:
        return None
    if isinstance(value, str):
        return ' '.join(value.split()).strip()
    if isinstance(value, dict):
        compactado = {}
        for key, item in value.items():
            cleaned = compact_prompt_context(item, depth=depth + 1)
            if cleaned in (None, '', [], {}):
                continue
            compactado[key] = cleaned
        return compactado
    if isinstance(value, list):
        limite = 3 if depth <= 1 else 4
        compactado = []
        for item in value:
            cleaned = compact_prompt_context(item, depth=depth + 1)
            if cleaned in (None, '', [], {}):
                continue
            compactado.append(cleaned)
            if len(compactado) >= limite:
                break
        return compactado
    return value


def normalize_model_for_provider(provider: str, model: str | None) -> str:
    provider_norm = clean_env_value(provider).lower() or 'deepseek'
    model_norm = clean_env_value(model)
    if provider_norm == 'deepseek':
        if (not model_norm) or model_norm.startswith('gpt-') or model_norm.startswith('o'):
            return 'deepseek-chat'
        return model_norm
    if (not model_norm) or model_norm.startswith('deepseek'):
        return 'gpt-4o-mini'
    return model_norm
