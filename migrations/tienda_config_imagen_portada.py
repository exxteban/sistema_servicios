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
        
        if dialect == 'mysql':
            try:
                db.session.execute(text("ALTER TABLE tienda_config ADD COLUMN imagen_portada VARCHAR(500) NULL"))
            except Exception as e:
                print(f"Columna imagen_portada ya existe o error (MySQL): {e}")
        else:
            # SQLite fallback
            try:
                db.session.execute(text("ALTER TABLE tienda_config ADD COLUMN imagen_portada VARCHAR(500)"))
            except Exception as e:
                print(f"Columna imagen_portada ya existe o error (SQLite): {e}")

        db.session.commit()
        print("Migración de imagen_portada completada.")

if __name__ == "__main__":
    run_migration()
