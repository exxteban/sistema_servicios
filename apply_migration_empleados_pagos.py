import os
import sys

# Agregar la ruta base si es necesario
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app, db

def run_migration():
    print("Iniciando migración: Creando tabla control_empleados_pagos...")
    app = create_app('default')
    with app.app_context():
        try:
            # Import models explicitly so SQLAlchemy knows about them before create_all
            import control_de_empleados.models
            db.create_all()
            print("✅ Migración completada exitosamente. Tablas creadas.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error durante la migración: {str(e)}")

if __name__ == "__main__":
    run_migration()
