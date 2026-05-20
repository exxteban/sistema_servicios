from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración mínima para conectar a la BD
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

def run_migration():
    print("Iniciando migración: Agregando columna codigo_barras...")
    
    with app.app_context():
        try:
            # Verificar si la columna ya existe
            check_query = text("""
                SELECT COUNT(*) 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'productos' 
                AND COLUMN_NAME = 'codigo_barras'
            """)
            
            result = db.session.execute(check_query).scalar()
            
            if result > 0:
                print("⚠️ La columna 'codigo_barras' ya existe. No es necesario migrar.")
                return

            # Agregar columna
            print("Ejecutando: ALTER TABLE productos ADD COLUMN codigo_barras VARCHAR(50)")
            db.session.execute(text("ALTER TABLE productos ADD COLUMN codigo_barras VARCHAR(50)"))
            
            # Agregar índice
            print("Ejecutando: CREATE INDEX ix_productos_codigo_barras ON productos(codigo_barras)")
            db.session.execute(text("CREATE INDEX ix_productos_codigo_barras ON productos(codigo_barras)"))
            
            db.session.commit()
            print("✅ Migración completada exitosamente.")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error durante la migración: {str(e)}")

if __name__ == "__main__":
    run_migration()
