import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from control_de_empleados.schema import ensure_control_empleados_schema


def run_migration():
    print("Iniciando migración: columnas de aguinaldo e IPS en control_empleados...")
    app = create_app('default')
    with app.app_context():
        ensure_control_empleados_schema()
        print("✅ Migración completada.")


if __name__ == "__main__":
    run_migration()
