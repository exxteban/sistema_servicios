"""
Configuración del Sistema de Inventario y Ventas
"""
import os
from datetime import timedelta

try:
    from dotenv import load_dotenv
    env_file_path = (os.environ.get('ENV_FILE_PATH') or '').strip()
    if env_file_path:
        if os.path.exists(env_file_path):
            load_dotenv(env_file_path, override=True)
        load_dotenv(override=False)
    else:
        if os.path.exists('/etc/sistema_cliente2.env'):
            load_dotenv('/etc/sistema_cliente2.env', override=False)
        load_dotenv(override=True)
except Exception:
    pass

basedir = os.path.abspath(os.path.dirname(__file__))

def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return _is_truthy(raw)

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except Exception:
        return default


def _env_samesite(name: str, default: str | None) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered == 'none':
        return 'None'
    if lowered == 'lax':
        return 'Lax'
    if lowered == 'strict':
        return 'Strict'
    return raw


def _clean_url(value: str | None) -> str:
    v = (value or '').strip()
    if not v:
        return ''
    while len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'", '`'):
        v = v[1:-1].strip()
    v = v.replace('`', '').strip()
    v = ''.join(v.split())
    return v.rstrip('/')


class Config:
    """Configuración base"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-secreta-cambiar-en-produccion'
    _csrf_time_limit = _env_int('WTF_CSRF_TIME_LIMIT', 0)
    WTF_CSRF_TIME_LIMIT = _csrf_time_limit if _csrf_time_limit > 0 else None
    
    # Base de datos
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'inventario.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAX_CONTENT_LENGTH = _env_int('MAX_CONTENT_LENGTH', 5 * 1024 * 1024)
    
    # Sesión
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)  # Sesión de 8 horas
    DEMO_SESSION_MINUTES = _env_int('DEMO_SESSION_MINUTES', 10)
    DEMO_BLOCK_MINUTES = _env_int('DEMO_BLOCK_MINUTES', 30)
    
    # Configuración de la aplicación
    ITEMS_PER_PAGE = 20
    TIMEZONE = os.environ.get('APP_TIMEZONE') or 'America/Asuncion'
    
    # IVA Paraguay
    IVA_10 = 10
    IVA_5 = 5
    IVA_EXENTA = 0

    # WhatsApp Cloud API
    WHATSAPP_ENABLED = _env_bool('WHATSAPP_ENABLED', False)
    WHATSAPP_PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '') or os.environ.get('WHATSAPP_PHONE_ID', '')
    WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.environ.get('WHATSAPP_WEBHOOK_VERIFY_TOKEN', '') or os.environ.get('WHATSAPP_VERIFY_TOKEN', '')
    WHATSAPP_DRY_RUN = _env_bool('WHATSAPP_DRY_RUN', False)
    WHATSAPP_RATE_LIMIT_PER_PHONE = _env_int('WHATSAPP_RATE_LIMIT_PER_PHONE', 20)
    WHATSAPP_RATE_LIMIT_GLOBAL = _env_int('WHATSAPP_RATE_LIMIT_GLOBAL', 500)
    WHATSAPP_SESION_HORAS = _env_int('WHATSAPP_SESION_HORAS', 24)
    WHATSAPP_CODIGO_EXPIRACION_DIAS = _env_int('WHATSAPP_CODIGO_EXPIRACION_DIAS', 30)
    WHATSAPP_MAX_INTENTOS_CODIGO = _env_int('WHATSAPP_MAX_INTENTOS_CODIGO', 3)
    WHATSAPP_ASESOR_TIMEOUT_SEGUNDOS = _env_int('WHATSAPP_ASESOR_TIMEOUT_SEGUNDOS', 180)
    WHATSAPP_ASESOR_HEARTBEAT_SEGUNDOS = _env_int('WHATSAPP_ASESOR_HEARTBEAT_SEGUNDOS', 30)
    WHATSAPP_ASESOR_MAX_CONVERSACIONES = _env_int('WHATSAPP_ASESOR_MAX_CONVERSACIONES', 5)

    # CRM WhatsApp
    CRM_ENABLED = _env_bool('CRM_ENABLED', True)

    # IA (GPT-5-mini)
    AI_ENABLED = _env_bool('AI_ENABLED', False)
    AI_PROVIDER = os.environ.get('AI_PROVIDER', 'openai')
    AI_MODEL = os.environ.get('AI_MODEL', 'gpt-4o-mini')
    AI_REASONING_EFFORT = os.environ.get('AI_REASONING_EFFORT', 'low')
    AI_MAX_TOKENS = _env_int('AI_MAX_TOKENS', 500)
    AI_TEMPERATURE = float(os.environ.get('AI_TEMPERATURE', '0.7'))
    DEEPSEEK_BASE_URL = _clean_url(os.environ.get('DEEPSEEK_BASE_URL')) or 'https://api.deepseek.com/v1'


class DevelopmentConfig(Config):
    """Configuración de desarrollo"""
    DEBUG = True


class ProductionConfig(Config):
    """Configuración de producción"""
    DEBUG = False
    SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', True)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = _env_samesite('SESSION_COOKIE_SAMESITE', 'Lax')
    REMEMBER_COOKIE_SECURE = _env_bool('REMEMBER_COOKIE_SECURE', True)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = _env_samesite('REMEMBER_COOKIE_SAMESITE', 'Lax')


class TestingConfig(Config):
    """Configuración de testing"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
