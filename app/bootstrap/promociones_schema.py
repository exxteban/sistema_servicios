"""Migraciones aditivas para promociones compartidas."""
from __future__ import annotations

from sqlalchemy import inspect, text

from app import db


def _columns(table_name: str) -> set[str]:
    inspector = inspect(db.engine)
    if not inspector.has_table(table_name):
        return set()
    return {column['name'] for column in inspector.get_columns(table_name)}


def _add_columns(table_name: str, definitions: dict[str, str]):
    existing = _columns(table_name)
    for name, definition in definitions.items():
        if name not in existing:
            db.session.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {name} {definition}'))
    db.session.commit()


def ensure_promociones_schema():
    from app.models.tienda_promocion import TiendaPromocionGastronomiaProducto

    TiendaPromocionGastronomiaProducto.__table__.create(bind=db.engine, checkfirst=True)
    _add_columns('tienda_promociones', {
        'cantidad_lleva': 'INTEGER NULL',
        'cantidad_paga': 'INTEGER NULL',
    })
    _add_columns('detalle_ventas', {
        'id_promocion_aplicada': 'INTEGER NULL',
        'promocion_descripcion': 'VARCHAR(255) NULL',
        'cantidad_bonificada': 'INTEGER NOT NULL DEFAULT 0',
    })
    _add_columns('gastronomia_pedido_items', {
        'precio_original': 'NUMERIC(15, 2) NOT NULL DEFAULT 0',
        'descuento_linea': 'NUMERIC(15, 2) NOT NULL DEFAULT 0',
        'id_promocion_aplicada': 'INTEGER NULL',
        'promocion_descripcion': 'VARCHAR(255) NULL',
        'cantidad_bonificada': 'INTEGER NOT NULL DEFAULT 0',
    })
