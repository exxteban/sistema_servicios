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
        try:
            db.session.execute(text("ALTER TABLE tienda_config ADD COLUMN hero_carrusel_animacion VARCHAR(20) NOT NULL DEFAULT 'fade'"))
            print('Columna hero_carrusel_animacion agregada.')
        except Exception as e:
            print(f'Columna hero_carrusel_animacion ya existe o error: {e}')

        db.session.commit()
        print('Migracion de animacion del hero carrusel completada.')


if __name__ == '__main__':
    run_migration()
