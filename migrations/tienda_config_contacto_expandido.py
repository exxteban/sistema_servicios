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
        nuevas_columnas = [
            ("titulo_footer", "VARCHAR(150)"),
            ("mostrar_titulo_footer", "BOOLEAN NOT NULL DEFAULT 1"),
            ("email_contacto", "VARCHAR(200)"),
            ("mostrar_email_contacto", "BOOLEAN NOT NULL DEFAULT 0"),
            ("sitio_web", "VARCHAR(255)"),
            ("mostrar_sitio_web", "BOOLEAN NOT NULL DEFAULT 0"),
            ("instagram_url", "VARCHAR(255)"),
            ("mostrar_instagram", "BOOLEAN NOT NULL DEFAULT 0"),
            ("facebook_url", "VARCHAR(255)"),
            ("mostrar_facebook", "BOOLEAN NOT NULL DEFAULT 0"),
            ("youtube_url", "VARCHAR(255)"),
            ("mostrar_youtube", "BOOLEAN NOT NULL DEFAULT 0"),
        ]

        for nombre, definicion in nuevas_columnas:
            try:
                db.session.execute(text(f"ALTER TABLE tienda_config ADD COLUMN {nombre} {definicion}"))
                print(f"Columna {nombre} agregada.")
            except Exception as e:
                print(f"Columna {nombre} ya existe o error: {e}")

        db.session.commit()
        print("Migración de contacto expandido completada.")


if __name__ == "__main__":
    run_migration()
