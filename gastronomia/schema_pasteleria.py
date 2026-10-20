"""Migraciones ligeras de las funciones de pasteleria/cafeteria.

Las fases siguientes del plan solo agregan columnas o tablas aqui, para no
engordar `gastronomia/schema.py`. Mismo patron que alla: SQLite y MySQL.
"""
from sqlalchemy import text

from app import db
from gastronomia.config_flags import FOTOS_ENCARGO_DEFAULT, OPCIONES_CANCELACION_DEFAULT, PASTELERIA_FLAGS
from gastronomia.schema import (
    _declares_nullability_or_default,
    _mysql_column_exists,
    _mysql_index_exists,
    _mysql_table_exists,
    _sqlite_table_exists,
)


CONFIG_TABLE = 'gastronomia_cliente_config'
ORDER_TABLE = 'gastronomia_pedidos'
ORDER_ITEM_TABLE = 'gastronomia_pedido_items'

CONFIG_COLUMN_MIGRATIONS = tuple(
    (flag, 'BOOLEAN NOT NULL DEFAULT 0') for flag in PASTELERIA_FLAGS
) + (
    ('encargos_anticipo_horas', 'INTEGER NOT NULL DEFAULT 0'),
    ('encargos_max_por_dia', 'INTEGER'),
    ('encargos_max_fotos', f'INTEGER NOT NULL DEFAULT {FOTOS_ENCARGO_DEFAULT}'),
    ('encargos_cancelacion_opciones', f"VARCHAR(120) NOT NULL DEFAULT '{OPCIONES_CANCELACION_DEFAULT}'"),
)

# Fase 1: encargos.
ORDER_COLUMN_MIGRATIONS = (
    ('es_encargo', 'BOOLEAN NOT NULL DEFAULT 0'),
    ('fecha_programada', 'DATETIME'),
)
ORDER_ITEM_COLUMN_MIGRATIONS = (
    ('texto_personalizado', 'VARCHAR(240)'),
)
ORDER_SCHEDULE_INDEX = 'ix_gastronomia_pedidos_fecha_programada'
ADELANTO_TABLE = 'gastronomia_pedido_adelantos'
ADELANTO_COLUMN_MIGRATIONS = (
    ('referencia', 'VARCHAR(100)'),
)


def ensure_pasteleria_schema():
    _crear_tablas()
    dialect = db.engine.dialect.name
    if dialect == 'sqlite':
        _ensure_sqlite_columns()
    elif dialect == 'mysql':
        _ensure_mysql_columns()


def _crear_tablas():
    from gastronomia.encargo_models import GastronomiaPedidoAdelanto, GastronomiaPedidoFoto

    if not _tabla_existe(ORDER_TABLE):
        # Base sin pedidos todavia: las tablas nuevas dependen de ella.
        return
    GastronomiaPedidoAdelanto.__table__.create(bind=db.engine, checkfirst=True)
    GastronomiaPedidoFoto.__table__.create(bind=db.engine, checkfirst=True)


def _tabla_existe(table: str) -> bool:
    if db.engine.dialect.name == 'mysql':
        return _mysql_table_exists(table)
    return _sqlite_table_exists(table)


def _ensure_sqlite_columns():
    _ensure_sqlite_table_columns(CONFIG_TABLE, CONFIG_COLUMN_MIGRATIONS)
    _ensure_sqlite_table_columns(ORDER_TABLE, ORDER_COLUMN_MIGRATIONS)
    _ensure_sqlite_table_columns(ORDER_ITEM_TABLE, ORDER_ITEM_COLUMN_MIGRATIONS)
    _ensure_sqlite_table_columns(ADELANTO_TABLE, ADELANTO_COLUMN_MIGRATIONS)
    if _sqlite_table_exists(ORDER_TABLE):
        db.session.execute(text(
            f'CREATE INDEX IF NOT EXISTS {ORDER_SCHEDULE_INDEX} ON {ORDER_TABLE}(fecha_programada)'
        ))
    db.session.commit()


def _ensure_mysql_columns():
    _ensure_mysql_table_columns(CONFIG_TABLE, CONFIG_COLUMN_MIGRATIONS)
    _ensure_mysql_table_columns(ORDER_TABLE, ORDER_COLUMN_MIGRATIONS)
    _ensure_mysql_table_columns(ORDER_ITEM_TABLE, ORDER_ITEM_COLUMN_MIGRATIONS)
    _ensure_mysql_table_columns(ADELANTO_TABLE, ADELANTO_COLUMN_MIGRATIONS)
    if _mysql_table_exists(ORDER_TABLE) and not _mysql_index_exists(ORDER_TABLE, ORDER_SCHEDULE_INDEX):
        db.session.execute(text(f'CREATE INDEX {ORDER_SCHEDULE_INDEX} ON {ORDER_TABLE}(fecha_programada)'))
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
