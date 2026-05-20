from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(basedir, 'inventario.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

def run_migration():
    with app.app_context():
        dialect = db.engine.dialect.name
        
        columnas = [
            ('es_destacado_tienda', 'BOOLEAN NOT NULL DEFAULT 0'),
            ('es_oferta_tienda', 'BOOLEAN NOT NULL DEFAULT 0')
        ]
        
        for col_name, col_def in columnas:
            if dialect == 'mysql':
                try:
                    db.session.execute(text(f"ALTER TABLE productos ADD COLUMN {col_name} {col_def}"))
                    print(f"Columna {col_name} agregada (MySQL).")
                except Exception as e:
                    print(f"Columna {col_name} ya existe o error (MySQL): {e}")
            else:
                try:
                    db.session.execute(text(f"ALTER TABLE productos ADD COLUMN {col_name} BOOLEAN NOT NULL DEFAULT 0"))
                    print(f"Columna {col_name} agregada (SQLite).")
                except Exception as e:
                    print(f"Columna {col_name} ya existe o error (SQLite): {e}")

        db.session.commit()
        print("Migración de destacados y ofertas completada.")

if __name__ == "__main__":
    run_migration()
