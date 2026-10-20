"""Migraciones ligeras de las funciones de pasteleria/cafeteria.

Las fases siguientes del plan solo agregan columnas o tablas aqui, para no
engordar `gastronomia/schema.py`. Mismo patron que alla: SQLite y MySQL.
"""
from sqlalchemy import text

from app import db
from gastronomia.config_flags import PASTELERIA_FLAGS
from gastronomia.schema import (
    _declares_nullability_or_default,
    _mysql_column_exists,
    _mysql_table_exists,
    _sqlite_table_exists,
)


CONFIG_TABLE = 'gastronomia_cliente_config'

CONFIG_COLUMN_MIGRATIONS = tuple(
    (flag, 'BOOLEAN NOT NULL DEFAULT 0') for flag in PASTELERIA_FLAGS
)


def ensure_pasteleria_schema():
    dialect = db.engine.dialect.name
    if dialect == 'sqlite':
        _ensure_sqlite_columns()
    elif dialect == 'mysql':
        _ensure_mysql_columns()


def _ensure_sqlite_columns():
    _ensure_sqlite_table_columns(CONFIG_TABLE, CONFIG_COLUMN_MIGRATIONS)
    db.session.commit()


def _ensure_mysql_columns():
    _ensure_mysql_table_columns(CONFIG_TABLE, CONFIG_COLUMN_MIGRATIONS)
    db.session.commit()


def _ensure_sqlite_table_columns(table: str, migrations) -> None:
    if not _sqlite_table_exists(table):
        return
    columns = {
        row[1]
        for row in db.session.execute(text(f'PRAGMA table_info({table})')).fetchall()
    }
    for column, column_type in migrations:
        if column not in columns:
            db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {column_type}'))


def _ensure_mysql_table_columns(table: str, migrations) -> None:
    if not _mysql_table_exists(table):
        return
    for column, column_type in migrations:
        if not _mysql_column_exists(table, column):
            add_type = column_type if _declares_nullability_or_default(column_type) else f'{column_type} NULL'
            db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {add_type}'))
