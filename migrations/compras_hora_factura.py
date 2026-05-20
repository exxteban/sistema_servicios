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


def _columnas_compras_sqlite():
    rows = db.session.execute(text("PRAGMA table_info(compras)")).fetchall()
    return {row[1] for row in rows}


def run_migration():
    with app.app_context():
        dialect = db.engine.dialect.name

        if dialect == 'sqlite':
            columnas = _columnas_compras_sqlite()
            if 'hora_compra' not in columnas:
                db.session.execute(text("ALTER TABLE compras ADD COLUMN hora_compra TIME"))
            if 'factura_imagen_url' not in columnas:
                db.session.execute(text("ALTER TABLE compras ADD COLUMN factura_imagen_url VARCHAR(500)"))
        else:
            try:
                db.session.execute(text("ALTER TABLE compras ADD COLUMN hora_compra TIME NULL"))
            except Exception as exc:
                print(f"Columna hora_compra ya existe o error: {exc}")
            try:
                db.session.execute(text("ALTER TABLE compras ADD COLUMN factura_imagen_url VARCHAR(500) NULL"))
            except Exception as exc:
                print(f"Columna factura_imagen_url ya existe o error: {exc}")

        db.session.commit()
        print("Migración de compras (hora/factura) completada.")


if __name__ == "__main__":
    run_migration()
