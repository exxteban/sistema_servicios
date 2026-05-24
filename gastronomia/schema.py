"""Migraciones ligeras del modulo Gastronomia."""
from sqlalchemy import text

from app import db


ORDER_COLUMN_MIGRATIONS = (
    ('fecha_inicio_preparacion', 'DATETIME'),
    ('fecha_listo', 'DATETIME'),
)


def ensure_gastronomia_schema():
    dialect = db.engine.dialect.name
    if dialect == 'sqlite':
        _ensure_sqlite_columns()
    elif dialect == 'mysql':
        _ensure_mysql_columns()


def _ensure_sqlite_columns():
    if not _sqlite_table_exists('gastronomia_pedidos'):
        return
    columns = {
        row[1]
        for row in db.session.execute(text('PRAGMA table_info(gastronomia_pedidos)')).fetchall()
    }
    for column, column_type in ORDER_COLUMN_MIGRATIONS:
        if column not in columns:
            db.session.execute(text(f'ALTER TABLE gastronomia_pedidos ADD COLUMN {column} {column_type}'))
    db.session.commit()


def _ensure_mysql_columns():
    if not _mysql_table_exists('gastronomia_pedidos'):
        return
    for column, column_type in ORDER_COLUMN_MIGRATIONS:
        if not _mysql_column_exists('gastronomia_pedidos', column):
            db.session.execute(text(f'ALTER TABLE gastronomia_pedidos ADD COLUMN {column} {column_type} NULL'))
    db.session.commit()


def _sqlite_table_exists(table_name: str) -> bool:
    return bool(db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"),
        {'table_name': table_name},
    ).scalar())


def _mysql_table_exists(table_name: str) -> bool:
    return bool(db.session.execute(text(
        """
        SELECT COUNT(*) FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name
        """
    ), {'table_name': table_name}).scalar())


def _mysql_column_exists(table_name: str, column_name: str) -> bool:
    return bool(db.session.execute(text(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name AND COLUMN_NAME = :column_name
        """
    ), {'table_name': table_name, 'column_name': column_name}).scalar())
