"""
Migración: reclasificar vueltos históricos en movimientos_caja.

Antes del cambio, los vueltos se grababan con:
    referencia_tipo = 'venta'
    tipo            = 'egreso'
    motivo          LIKE 'Vuelto Venta #%'

A partir del cambio, se graban con:
    referencia_tipo = 'vuelto'

Este script actualiza los registros históricos para que coincidan con
el nuevo formato, de modo que los filtros de informes funcionen
uniformemente sin depender del texto del motivo.

Es idempotente: puede correrse más de una vez sin efecto secundario.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

load_dotenv()

app = Flask(__name__)
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app.config['SQLALCHEMY_DATABASE_URI'] = (
    os.environ.get('DATABASE_URL')
    or 'sqlite:///' + os.path.join(basedir, 'inventario.db')
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


def run_migration() -> None:
    with app.app_context():
        dialect = db.engine.dialect.name

        if dialect == 'sqlite':
            result = db.session.execute(
                text(
                    """
                    UPDATE movimientos_caja
                    SET referencia_tipo = 'vuelto'
                    WHERE referencia_tipo = 'venta'
                      AND tipo = 'egreso'
                      AND LOWER(motivo) LIKE 'vuelto%'
                    """
                )
            )
        else:
            # PostgreSQL / MySQL — LOWER() también disponible
            result = db.session.execute(
                text(
                    """
                    UPDATE movimientos_caja
                    SET referencia_tipo = 'vuelto'
                    WHERE referencia_tipo = 'venta'
                      AND tipo = 'egreso'
                      AND LOWER(motivo) LIKE 'vuelto%'
                    """
                )
            )

        db.session.commit()
        filas = result.rowcount if result.rowcount is not None else -1
        print(f"Migración caja_reclasificar_vueltos completada. Filas actualizadas: {filas}")


if __name__ == '__main__':
    run_migration()
