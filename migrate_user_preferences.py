"""
Script para agregar el campo dashboard_range_preference a la tabla usuarios
"""
import sys
import os

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        # Intentar agregar la columna usando text()
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN dashboard_range_preference VARCHAR(20) DEFAULT 'hoy'"))
            conn.commit()
        print("✓ Columna dashboard_range_preference agregada exitosamente")
    except Exception as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            print("✓ La columna dashboard_range_preference ya existe")
        else:
            print(f"✗ Error al agregar columna: {e}")
            raise
