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
            ('hero_visual_tipo', "VARCHAR(20) NOT NULL DEFAULT 'imagen'"),
            ('hero_carrusel_producto_ids', 'TEXT'),
            ('hero_carrusel_velocidad_segundos', 'INTEGER NOT NULL DEFAULT 5'),
        ]

        for nombre, definicion in nuevas_columnas:
            try:
                db.session.execute(text(f'ALTER TABLE tienda_config ADD COLUMN {nombre} {definicion}'))
                print(f'Columna {nombre} agregada.')
            except Exception as e:
                print(f'Columna {nombre} ya existe o error: {e}')

        db.session.commit()
        print('Migracion de hero carrusel completada.')


if __name__ == '__main__':
    run_migration()
