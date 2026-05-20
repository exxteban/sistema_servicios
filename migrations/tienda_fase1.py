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
            productos_existe = db.session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'productos'
                    """
                )
            ).scalar()
            tienda_cols = [
                ('publicado_tienda', 'TINYINT(1) NOT NULL DEFAULT 0'),
                ('descripcion_tienda', 'TEXT NULL'),
                ('orden_tienda', 'INT NOT NULL DEFAULT 0'),
            ]
            if productos_existe:
                for nombre, definicion in tienda_cols:
                    existe = db.session.execute(
                        text(
                            f"""
                            SELECT COUNT(*) FROM information_schema.COLUMNS
                            WHERE TABLE_SCHEMA = DATABASE()
                              AND TABLE_NAME = 'productos'
                              AND COLUMN_NAME = '{nombre}'
                            """
                        )
                    ).scalar()
                    if not existe:
                        db.session.execute(text(f"ALTER TABLE productos ADD COLUMN {nombre} {definicion}"))

            db.session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS tienda_config (
                        id_config INT AUTO_INCREMENT PRIMARY KEY,
                        id_cliente INT NOT NULL UNIQUE,
                        slug VARCHAR(80) NOT NULL UNIQUE,
                        nombre_tienda VARCHAR(200) NULL,
                        logo_url VARCHAR(500) NULL,
                        color_primario VARCHAR(20) NOT NULL DEFAULT '#6366f1',
                        telefono_whatsapp VARCHAR(30) NULL,
                        mensaje_whatsapp VARCHAR(500) NULL,
                        texto_portada TEXT NULL,
                        estilo_tienda VARCHAR(50) NOT NULL DEFAULT 'moderno',
                        activa TINYINT(1) NOT NULL DEFAULT 1,
                        fecha_creacion DATETIME,
                        fecha_modificacion DATETIME,
                        CONSTRAINT fk_tienda_config_cliente
                            FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
                            ON DELETE CASCADE
                    )
                    """
                )
            )
            if productos_existe:
                db.session.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS producto_imagenes (
                            id_imagen INT AUTO_INCREMENT PRIMARY KEY,
                            id_producto INT NOT NULL,
                            url VARCHAR(500) NOT NULL,
                            orden INT NOT NULL DEFAULT 0,
                            activa TINYINT(1) NOT NULL DEFAULT 1,
                            fecha_creacion DATETIME,
                            INDEX ix_producto_imagenes_producto_activa (id_producto, activa),
                            CONSTRAINT fk_producto_imagenes_producto
                                FOREIGN KEY (id_producto) REFERENCES productos(id_producto)
                                ON DELETE CASCADE
                        )
                        """
                    )
                )
            if productos_existe:
                db.session.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS tienda_leads (
                            id_lead INT AUTO_INCREMENT PRIMARY KEY,
                            id_cliente INT NOT NULL,
                            id_producto INT NULL,
                            nombre_contacto VARCHAR(200) NOT NULL,
                            telefono_contacto VARCHAR(50) NULL,
                            email_contacto VARCHAR(120) NULL,
                            mensaje TEXT NULL,
                            leido TINYINT(1) NOT NULL DEFAULT 0,
                            fecha_creacion DATETIME,
                            INDEX ix_tienda_leads_cliente_leido (id_cliente, leido),
                            CONSTRAINT fk_tienda_leads_cliente
                                FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
                                ON DELETE CASCADE,
                            CONSTRAINT fk_tienda_leads_producto
                                FOREIGN KEY (id_producto) REFERENCES productos(id_producto)
                                ON DELETE SET NULL
                        )
                        """
                    )
                )

            db.session.commit()
            return

        if dialect == 'sqlite':
            productos_existe = db.session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='productos'")
            ).scalar()
            if productos_existe:
                cols_prod = [row[1] for row in db.session.execute(text("PRAGMA table_info(productos)")).fetchall()]
                if 'publicado_tienda' not in cols_prod:
                    db.session.execute(text("ALTER TABLE productos ADD COLUMN publicado_tienda BOOLEAN NOT NULL DEFAULT 0"))
                if 'descripcion_tienda' not in cols_prod:
                    db.session.execute(text("ALTER TABLE productos ADD COLUMN descripcion_tienda TEXT"))
                if 'orden_tienda' not in cols_prod:
                    db.session.execute(text("ALTER TABLE productos ADD COLUMN orden_tienda INTEGER NOT NULL DEFAULT 0"))

            db.session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS tienda_config (
                        id_config INTEGER PRIMARY KEY AUTOINCREMENT,
                        id_cliente INTEGER NOT NULL UNIQUE,
                        slug VARCHAR(80) NOT NULL UNIQUE,
                        nombre_tienda VARCHAR(200),
                        logo_url VARCHAR(500),
                        color_primario VARCHAR(20) NOT NULL DEFAULT '#6366f1',
                        telefono_whatsapp VARCHAR(30),
                        mensaje_whatsapp VARCHAR(500),
                        texto_portada TEXT,
                        estilo_tienda VARCHAR(50) NOT NULL DEFAULT 'moderno',
                        activa BOOLEAN NOT NULL DEFAULT 1,
                        fecha_creacion DATETIME,
                        fecha_modificacion DATETIME,
                        FOREIGN KEY(id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE
                    )
                    """
                )
            )
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_tienda_config_id_cliente ON tienda_config(id_cliente)"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_tienda_config_slug ON tienda_config(slug)"))

            if productos_existe:
                db.session.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS producto_imagenes (
                            id_imagen INTEGER PRIMARY KEY AUTOINCREMENT,
                            id_producto INTEGER NOT NULL,
                            url VARCHAR(500) NOT NULL,
                            orden INTEGER NOT NULL DEFAULT 0,
                            activa BOOLEAN NOT NULL DEFAULT 1,
                            fecha_creacion DATETIME,
                            FOREIGN KEY(id_producto) REFERENCES productos(id_producto) ON DELETE CASCADE
                        )
                        """
                    )
                )
                db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_producto_imagenes_producto_activa ON producto_imagenes(id_producto, activa)"))

            if productos_existe:
                db.session.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS tienda_leads (
                            id_lead INTEGER PRIMARY KEY AUTOINCREMENT,
                            id_cliente INTEGER NOT NULL,
                            id_producto INTEGER,
                            nombre_contacto VARCHAR(200) NOT NULL,
                            telefono_contacto VARCHAR(50),
                            email_contacto VARCHAR(120),
                            mensaje TEXT,
                            leido BOOLEAN NOT NULL DEFAULT 0,
                            fecha_creacion DATETIME,
                            FOREIGN KEY(id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
                            FOREIGN KEY(id_producto) REFERENCES productos(id_producto) ON DELETE SET NULL
                        )
                        """
                    )
                )
                db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_tienda_leads_cliente_leido ON tienda_leads(id_cliente, leido)"))
            db.session.commit()


if __name__ == "__main__":
    run_migration()
