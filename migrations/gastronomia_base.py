import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

ENV_FILE_CANDIDATES = (
    os.environ.get('ENV_FILE_PATH'),
    '/etc/sistema_cliente2.env',
    BASE_DIR / '.env',
    BASE_DIR.parent / '.env',
)


def _load_environment() -> None:
    for candidate in ENV_FILE_CANDIDATES:
        if candidate and Path(candidate).exists():
            load_dotenv(candidate, override=False)
    load_dotenv(override=False)


def _database_url() -> str:
    return os.environ.get('DATABASE_URL') or f"sqlite:///{(BASE_DIR / 'inventario.db').as_posix()}"


def _masked_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if not parsed.username:
        return database_url
    host = parsed.hostname or ''
    port = f':{parsed.port}' if parsed.port else ''
    db_name = parsed.path or ''
    return f'{parsed.scheme}://{parsed.username}:***@{host}{port}{db_name}'


def _backup_sqlite(parsed_url, backup_dir: Path) -> Path:
    raw_path = unquote(parsed_url.path or '')
    if os.name == 'nt' and len(raw_path) >= 4 and raw_path[0] == '/' and raw_path[2] == ':':
        raw_path = raw_path[1:]
    db_path = Path(raw_path)
    if not db_path.exists():
        raise RuntimeError(f'No existe el archivo SQLite: {db_path}')
    backup_path = backup_dir / f'{db_path.stem}_pre_gastronomia_{_timestamp()}{db_path.suffix or ".db"}'
    shutil.copy2(db_path, backup_path)
    return backup_path


def _backup_mysql(parsed_url, backup_dir: Path) -> Path:
    dump_cmd = shutil.which('mysqldump') or shutil.which('mariadb-dump')
    if not dump_cmd:
        raise RuntimeError('No se encontro mysqldump/mariadb-dump para respaldar MySQL.')
    db_name = unquote((parsed_url.path or '').lstrip('/'))
    if not db_name or not parsed_url.hostname or not parsed_url.username:
        raise RuntimeError('DATABASE_URL incompleto para backup MySQL.')
    backup_path = backup_dir / f'{db_name}_pre_gastronomia_{_timestamp()}.sql'
    env = os.environ.copy()
    env['MYSQL_PWD'] = unquote(parsed_url.password or '')
    args = [
        dump_cmd,
        f'--host={parsed_url.hostname}',
        f'--port={parsed_url.port or 3306}',
        f'--user={unquote(parsed_url.username)}',
        '--single-transaction',
        '--routines',
        '--events',
        '--triggers',
        db_name,
    ]
    with backup_path.open('w', encoding='utf-8') as output:
        subprocess.run(args, check=True, stdout=output, env=env)
    if backup_path.stat().st_size <= 0:
        backup_path.unlink(missing_ok=True)
        raise RuntimeError('El backup MySQL salio vacio.')
    return backup_path


def _timestamp() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def _backup_database(database_url: str) -> Path | None:
    if os.environ.get('SKIP_GASTRONOMIA_BACKUP') == '1':
        return None
    backup_dir = Path(os.environ.get('BACKUP_DIR') or BASE_DIR / 'backups')
    backup_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(database_url)
    if parsed.scheme.startswith('sqlite'):
        return _backup_sqlite(parsed, backup_dir)
    if parsed.scheme.startswith('mysql'):
        return _backup_mysql(parsed, backup_dir)
    raise RuntimeError(f'Dialecto no soportado para backup: {parsed.scheme}')


def run_migration() -> None:
    _load_environment()
    database_url = _database_url()
    print(f'Base detectada: {_masked_database_url(database_url)}')
    backup_path = _backup_database(database_url)
    if backup_path:
        print(f'Backup pre-migracion OK: {backup_path}')

    os.environ['DATABASE_URL'] = database_url
    from app import create_app, db
    from app.models.producto_presentacion import ProductoPresentacionStock
    from gastronomia import models as gastronomia_models
    from gastronomia.channel_models import GastronomiaProductoPrecioCanal
    from gastronomia import stock_models as gastronomia_stock_models
    from gastronomia.schema import ensure_gastronomia_schema

    config_name = os.environ.get('FLASK_CONFIG') or os.environ.get('APP_CONFIG') or 'production'
    app = create_app(config_name)
    tables = [
        gastronomia_models.GastronomiaClienteConfig.__table__,
        gastronomia_models.GastronomiaCategoria.__table__,
        gastronomia_models.GastronomiaProducto.__table__,
        GastronomiaProductoPrecioCanal.__table__,
        gastronomia_models.GastronomiaGrupoOpciones.__table__,
        gastronomia_models.GastronomiaOpcionProducto.__table__,
        gastronomia_models.GastronomiaMesa.__table__,
        gastronomia_models.GastronomiaRepartidor.__table__,
        gastronomia_models.GastronomiaPedido.__table__,
        gastronomia_models.GastronomiaPedidoItem.__table__,
        gastronomia_models.GastronomiaPedidoItemModificador.__table__,
        gastronomia_models.GastronomiaPedidoEvento.__table__,
        gastronomia_models.GastronomiaPedidoPago.__table__,
        ProductoPresentacionStock.__table__,
        gastronomia_stock_models.GastronomiaRecetaInsumo.__table__,
        gastronomia_stock_models.GastronomiaOpcionInsumo.__table__,
        gastronomia_stock_models.GastronomiaPedidoItemConsumo.__table__,
    ]
    with app.app_context():
        for table in tables:
            table.create(bind=db.engine, checkfirst=True)
        ensure_gastronomia_schema()
        db.session.commit()
    print('Migracion base de Gastronomia completada.')


if __name__ == '__main__':
    run_migration()
