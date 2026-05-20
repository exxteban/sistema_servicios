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
            existe = db.session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'productos'
                      AND COLUMN_NAME = 'vistas_tienda'
                    """
                )
            ).scalar()
            if not existe:
                db.session.execute(text("ALTER TABLE productos ADD COLUMN vistas_tienda INT NOT NULL DEFAULT 0"))
                db.session.commit()
                print("Migración MySQL: vistas_tienda agregada a productos.")
            else:
                print("MySQL: vistas_tienda ya existe.")
            columnas_tienda = [
                ('titulo_footer', "VARCHAR(150) NULL"),
                ('mostrar_titulo_footer', "TINYINT(1) NOT NULL DEFAULT 1"),
                ('email_contacto', "VARCHAR(200) NULL"),
                ('mostrar_email_contacto', "TINYINT(1) NOT NULL DEFAULT 0"),
                ('sitio_web', "VARCHAR(255) NULL"),
                ('mostrar_sitio_web', "TINYINT(1) NOT NULL DEFAULT 0"),
                ('instagram_url', "VARCHAR(255) NULL"),
                ('mostrar_instagram', "TINYINT(1) NOT NULL DEFAULT 0"),
                ('facebook_url', "VARCHAR(255) NULL"),
                ('mostrar_facebook', "TINYINT(1) NOT NULL DEFAULT 0"),
                ('youtube_url', "VARCHAR(255) NULL"),
                ('mostrar_youtube', "TINYINT(1) NOT NULL DEFAULT 0"),
            ]
            for nombre, definicion in columnas_tienda:
                existe = db.session.execute(
                    text(
                        f"""
                        SELECT COUNT(*) FROM information_schema.COLUMNS
                        WHERE TABLE_SCHEMA = DATABASE()
                          AND TABLE_NAME = 'tienda_config'
                          AND COLUMN_NAME = '{nombre}'
                        """
                    )
                ).scalar()
                if not existe:
                    db.session.execute(text(f"ALTER TABLE tienda_config ADD COLUMN {nombre} {definicion}"))
                    db.session.commit()
                    print(f"Migración MySQL: {nombre} agregada a tienda_config.")
                else:
                    print(f"MySQL: {nombre} ya existe.")
        else:
            # SQLite u otros
            try:
                # Verificamos si la columna existe intentando seleccionarla
                db.session.execute(text("SELECT vistas_tienda FROM productos LIMIT 1"))
                print("SQLite: vistas_tienda ya existe.")
            except Exception:
                db.session.rollback()
                db.session.execute(text("ALTER TABLE productos ADD COLUMN vistas_tienda INTEGER NOT NULL DEFAULT 0"))
                db.session.commit()
                print("Migración SQLite: vistas_tienda agregada a productos.")

if __name__ == '__main__':
    run_migration()
