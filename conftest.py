import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
TEST_DB_DIR = BASE_DIR / ".pytest_cache"
TEST_DB_DIR.mkdir(parents=True, exist_ok=True)


def _db_url(nombre):
    return f"sqlite:///{(TEST_DB_DIR / nombre).as_posix()}"


TEST_DB_URL = _db_url("test_runtime.sqlite3")

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("APP_TIMEZONE", "America/Asuncion")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("LOG_REQUEST_ACCESS", "0")
os.environ.setdefault("LOG_REQUEST_VERBOSE", "0")
os.environ.setdefault("LOG_REQUEST_BODY", "0")
os.environ.setdefault("LOG_RESPONSE_ERROR_BODY", "0")
os.environ.setdefault("CRM_ENABLED", "1")
os.environ.setdefault("WHATSAPP_ENABLED", "0")
os.environ.setdefault("WHATSAPP_DRY_RUN", "1")
os.environ.setdefault("AI_ENABLED", "0")
os.environ.setdefault("CACHE_TYPE", "SimpleCache")


def pytest_configure(config):
    # Con pytest-xdist cada worker (gw0, gw1...) usa su propio archivo para no pisarse.
    # Se resuelve acá porque el id del worker no existe todavía cuando se importa este archivo.
    # Los workers heredan el DATABASE_URL del proceso principal: sólo se cambia si es el de tests.
    workerinput = getattr(config, "workerinput", None)
    if workerinput and os.environ.get("DATABASE_URL") == TEST_DB_URL:
        os.environ["DATABASE_URL"] = _db_url(f"test_runtime_{workerinput['workerid']}.sqlite3")
