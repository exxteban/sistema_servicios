"""Migraciones ligeras especificas de tienda online."""
from sqlalchemy import text

from app import db


TIENDA_CONFIG_COLUMNS = (
    ('tienda_delivery_activo', 'BOOLEAN NOT NULL DEFAULT 1', 'TINYINT(1) NOT NULL DEFAULT 1'),
    ('tienda_retiro_activo', 'BOOLEAN NOT NULL DEFAULT 1', 'TINYINT(1) NOT NULL DEFAULT 1'),
)


def ensure_tienda_config_schema():
    dialect = db.engine.dialect.name
    if dialect == 'sqlite':
        _ensure_sqlite_tienda_config_columns()
    elif dialect == 'mysql':
        _ensure_mysql_tienda_config_columns()


def _ensure_sqlite_tienda_config_columns():
    if not _sqlite_table_exists('tienda_config'):
        return
    columns = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(tienda_config)')).fetchall()
    }
    for column, sqlite_type, _mysql_type in TIENDA_CONFIG_COLUMNS:
        if column not in columns:
            db.session.execute(text(f'ALTER TABLE tienda_config ADD COLUMN {column} {sqlite_type}'))
    db.session.commit()


def _ensure_mysql_tienda_config_columns():
    if not _mysql_table_exists('tienda_config'):
        return
    for column, _sqlite_type, mysql_type in TIENDA_CONFIG_COLUMNS:
        if not _mysql_column_exists('tienda_config', column):
            db.session.execute(text(f'ALTER TABLE tienda_config ADD COLUMN {column} {mysql_type}'))
    db.session.commit()


def _sqlite_table_exists(table_name: str) -> bool:
    return db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
        {'table_name': table_name},
    ).scalar() is not None


def _mysql_scalar(query: str):
    return db.session.execute(text(query)).scalar()


def _mysql_table_exists(table_name: str) -> bool:
    query = f"""
    SELECT COUNT(*) FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = '{table_name}'
    """
    return bool(_mysql_scalar(query))


def _mysql_column_exists(table_name: str, column_name: str) -> bool:
    query = f"""
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = '{table_name}'
      AND COLUMN_NAME = '{column_name}'
    """
    return bool(_mysql_scalar(query))
