import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text


BASE_DIR = Path(__file__).resolve().parent.parent
EXPECTED_TABLES = {
    'agenda_actividades',
    'ventas',
    'productos',
    'reparaciones',
    'whatsapp_conversaciones',
    'whatsapp_mensajes',
}
ENV_FILE_CANDIDATES = (
    '/etc/sistema_cliente2.env',
    BASE_DIR / '.env',
    BASE_DIR.parent / '.env',
)

INDEXES = [
    (
        'agenda_actividades',
        'ix_agenda_actividades_estado_fecha_inicio',
        'CREATE INDEX ix_agenda_actividades_estado_fecha_inicio ON agenda_actividades(estado, fecha_inicio)',
    ),
    (
        'ventas',
        'ix_ventas_estado_fecha_venta',
        'CREATE INDEX ix_ventas_estado_fecha_venta ON ventas(estado, fecha_venta)',
    ),
    (
        'productos',
        'ix_productos_activo_publicado_orden',
        'CREATE INDEX ix_productos_activo_publicado_orden ON productos(activo, publicado_tienda, orden_tienda)',
    ),
    (
        'reparaciones',
        'ix_reparaciones_estado_fecha_ingreso',
        'CREATE INDEX ix_reparaciones_estado_fecha_ingreso ON reparaciones(estado, fecha_ingreso)',
    ),
    (
        'reparaciones',
        'ix_reparaciones_cliente_fecha_ingreso',
        'CREATE INDEX ix_reparaciones_cliente_fecha_ingreso ON reparaciones(cliente_id, fecha_ingreso)',
    ),
    (
        'whatsapp_conversaciones',
        'ix_whatsapp_conversaciones_activa_modo_ultima_actividad',
        'CREATE INDEX ix_whatsapp_conversaciones_activa_modo_ultima_actividad ON whatsapp_conversaciones(activa, modo, ultima_actividad)',
    ),
    (
        'whatsapp_mensajes',
        'ix_whatsapp_mensajes_conversacion_direccion_created_at',
        'CREATE INDEX ix_whatsapp_mensajes_conversacion_direccion_created_at ON whatsapp_mensajes(id_conversacion, direccion, created_at)',
    ),
]


def _load_environment():
    env_file_path = (os.environ.get('ENV_FILE_PATH') or '').strip()
    if env_file_path:
        if os.path.exists(env_file_path):
            load_dotenv(env_file_path, override=True)
    for candidate in ENV_FILE_CANDIDATES:
        if os.path.exists(candidate):
            load_dotenv(candidate, override=False)
    load_dotenv(override=False)


def _sqlite_existing_tables(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def _iter_sqlite_candidates():
    seen_paths = set()
    direct_candidates = [
        BASE_DIR / 'instance' / 'inventario.db',
        BASE_DIR / 'inventario.db',
        BASE_DIR / 'data' / 'inventario.db',
        BASE_DIR.parent / 'instance' / 'inventario.db',
        BASE_DIR.parent / 'inventario.db',
    ]
    for path in direct_candidates:
        resolved = path.resolve()
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        yield path

    glob_patterns = (
        '*.db',
        'instance/*.db',
        'data/*.db',
        '*/instance/*.db',
    )
    for root in (BASE_DIR, BASE_DIR.parent):
        for pattern in glob_patterns:
            for path in root.glob(pattern):
                resolved = path.resolve()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                yield path


def _resolve_database_uri() -> str:
    configured_uri = (os.environ.get('DATABASE_URL') or '').strip()
    if configured_uri:
        return configured_uri

    ranked = []
    for path in _iter_sqlite_candidates():
        tables = _sqlite_existing_tables(path)
        ranked.append((len(EXPECTED_TABLES.intersection(tables)), len(tables), path))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)

    if ranked and (ranked[0][0] > 0 or ranked[0][1] > 0):
        return f"sqlite:///{ranked[0][2].as_posix()}"
    return f"sqlite:///{(BASE_DIR / 'inventario.db').as_posix()}"


def _mask_database_uri(uri: str) -> str:
    if '://' not in uri:
        return uri
    scheme, rest = uri.split('://', 1)
    if '@' not in rest:
        return uri
    credentials, suffix = rest.split('@', 1)
    if ':' not in credentials:
        return f'{scheme}://***@{suffix}'
    username = credentials.split(':', 1)[0]
    return f'{scheme}://{username}:***@{suffix}'


_load_environment()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = _resolve_database_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


def _index_exists_sqlite(index_name: str) -> bool:
    return bool(
        db.session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type = 'index' AND name = :index_name
                """
            ),
            {'index_name': index_name},
        ).scalar()
    )


def _index_exists_mysql(table_name: str, index_name: str) -> bool:
    return bool(
        db.session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = :table_name
                  AND INDEX_NAME = :index_name
                """
            ),
            {'table_name': table_name, 'index_name': index_name},
        ).scalar()
    )


def _index_exists(dialect: str, table_name: str, index_name: str) -> bool:
    if dialect == 'sqlite':
        return _index_exists_sqlite(index_name)
    if dialect == 'mysql':
        return _index_exists_mysql(table_name, index_name)
    raise RuntimeError(f'Dialecto no soportado para esta migración: {dialect}')


def _table_exists_sqlite(table_name: str) -> bool:
    return bool(
        db.session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type = 'table' AND name = :table_name
                """
            ),
            {'table_name': table_name},
        ).scalar()
    )


def _table_exists_mysql(table_name: str) -> bool:
    return bool(
        db.session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = :table_name
                """
            ),
            {'table_name': table_name},
        ).scalar()
    )


def _table_exists(dialect: str, table_name: str) -> bool:
    if dialect == 'sqlite':
        return _table_exists_sqlite(table_name)
    if dialect == 'mysql':
        return _table_exists_mysql(table_name)
    raise RuntimeError(f'Dialecto no soportado para esta migración: {dialect}')


def _existing_target_tables(dialect: str) -> set[str]:
    return {
        table_name for table_name, _, _ in INDEXES
        if _table_exists(dialect, table_name)
    }


def run_migration():
    with app.app_context():
        dialect = db.engine.dialect.name
        print(f'Aplicando índices de performance sobre {dialect}...')
        print(f'Conexión detectada: {_mask_database_uri(app.config["SQLALCHEMY_DATABASE_URI"])}')
        existing_tables = _existing_target_tables(dialect)
        if not existing_tables:
            raise RuntimeError(
                'No se encontró ninguna de las tablas objetivo en la base conectada. '
                + f'Revisá DATABASE_URL/ENV_FILE_PATH. Conexión actual: {_mask_database_uri(app.config["SQLALCHEMY_DATABASE_URI"])}'
            )

        for table_name, index_name, create_sql in INDEXES:
            try:
                if table_name not in existing_tables:
                    print(f'· {index_name}: omitido, tabla {table_name} no existe en este servidor')
                    continue
                if _index_exists(dialect, table_name, index_name):
                    print(f'· {index_name}: ya existe')
                    continue
                db.session.execute(text(create_sql))
                db.session.commit()
                print(f'✓ {index_name}: creado')
            except Exception as exc:
                db.session.rollback()
                print(f'✗ {index_name}: error {exc}')
                raise

        print('Migración de índices completada.')


if __name__ == '__main__':
    run_migration()
