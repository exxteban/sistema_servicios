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
        
        # Add new columns to tienda_config
        if dialect == 'mysql':
            try:
                db.session.execute(text("ALTER TABLE tienda_config ADD COLUMN mensaje_whatsapp VARCHAR(500) NULL"))
            except Exception as e:
                print(f"Columna mensaje_whatsapp ya existe o error: {e}")
                
            try:
                db.session.execute(text("ALTER TABLE tienda_config ADD COLUMN estilo_tienda VARCHAR(50) NOT NULL DEFAULT 'moderno'"))
            except Exception as e:
                print(f"Columna estilo_tienda ya existe o error: {e}")
        else:
            try:
                db.session.execute(text("ALTER TABLE tienda_config ADD COLUMN mensaje_whatsapp VARCHAR(500)"))
            except Exception as e:
                print(f"Columna mensaje_whatsapp ya existe o error: {e}")
                
            try:
                db.session.execute(text("ALTER TABLE tienda_config ADD COLUMN estilo_tienda VARCHAR(50) NOT NULL DEFAULT 'moderno'"))
            except Exception as e:
                print(f"Columna estilo_tienda ya existe o error: {e}")

        db.session.commit()
        print("Migración tienda_config completada.")

if __name__ == "__main__":
    run_migration()