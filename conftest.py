import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
TEST_DB_PATH = BASE_DIR / ".pytest_cache" / "test_runtime.sqlite3"
TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB_PATH.as_posix()}")
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
