from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
import os

from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(basedir, 'inventario.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


CREATE_PROMOCIONES_SQLITE = """
CREATE TABLE tienda_promociones (
    id_promocion INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cliente INTEGER NOT NULL,
    nombre VARCHAR(160) NOT NULL,
    descripcion_corta TEXT NULL,
    tipo VARCHAR(30) NOT NULL DEFAULT 'porcentaje',
    valor NUMERIC(10, 2) NOT NULL,
    fecha_inicio DATETIME NOT NULL,
    fecha_fin DATETIME NOT NULL,
    activa BOOLEAN NOT NULL DEFAULT 1,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE
)
"""

CREATE_PROMOCIONES_MYSQL = """
CREATE TABLE tienda_promociones (
    id_promocion INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente INT NOT NULL,
    nombre VARCHAR(160) NOT NULL,
    descripcion_corta TEXT NULL,
    tipo VARCHAR(30) NOT NULL DEFAULT 'porcentaje',
    valor DECIMAL(10, 2) NOT NULL,
    fecha_inicio DATETIME NOT NULL,
    fecha_fin DATETIME NOT NULL,
    activa BOOLEAN NOT NULL DEFAULT 1,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_tienda_promociones_cliente FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE
)
"""

CREATE_PROMOCION_PRODUCTOS_SQLITE = """
CREATE TABLE tienda_promocion_productos (
    id_relacion INTEGER PRIMARY KEY AUTOINCREMENT,
    id_promocion INTEGER NOT NULL,
    id_producto INTEGER NOT NULL,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(id_promocion) REFERENCES tienda_promociones(id_promocion) ON DELETE CASCADE,
    FOREIGN KEY(id_producto) REFERENCES productos(id_producto) ON DELETE CASCADE,
    CONSTRAINT uq_tienda_promocion_producto UNIQUE (id_promocion, id_producto)
)
"""

CREATE_PROMOCION_PRODUCTOS_MYSQL = """
CREATE TABLE tienda_promocion_productos (
    id_relacion INT AUTO_INCREMENT PRIMARY KEY,
    id_promocion INT NOT NULL,
    id_producto INT NOT NULL,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tienda_promocion_productos_promocion FOREIGN KEY (id_promocion) REFERENCES tienda_promociones(id_promocion) ON DELETE CASCADE,
    CONSTRAINT fk_tienda_promocion_productos_producto FOREIGN KEY (id_producto) REFERENCES productos(id_producto) ON DELETE CASCADE,
    CONSTRAINT uq_tienda_promocion_producto UNIQUE (id_promocion, id_producto)
)
"""


def _ensure_index(index_name: str, create_sql: str):
    inspector = inspect(db.engine)
    existing_indexes = {
        item['name']
        for table_name in ('tienda_promociones', 'tienda_promocion_productos')
        if inspector.has_table(table_name)
        for item in inspector.get_indexes(table_name)
    }
    if index_name in existing_indexes:
        print(f"Índice {index_name} ya existe.")
        return
    db.session.execute(text(create_sql))
    print(f"Índice {index_name} creado.")


def run_migration():
    with app.app_context():
        inspector = inspect(db.engine)
        dialect = db.engine.dialect.name

        if not inspector.has_table('tienda_promociones'):
            sql = CREATE_PROMOCIONES_MYSQL if dialect == 'mysql' else CREATE_PROMOCIONES_SQLITE
            db.session.execute(text(sql))
            print('Tabla tienda_promociones creada.')
        else:
            print('Tabla tienda_promociones ya existe.')

        if not inspector.has_table('tienda_promocion_productos'):
            sql = CREATE_PROMOCION_PRODUCTOS_MYSQL if dialect == 'mysql' else CREATE_PROMOCION_PRODUCTOS_SQLITE
            db.session.execute(text(sql))
            print('Tabla tienda_promocion_productos creada.')
        else:
            print('Tabla tienda_promocion_productos ya existe.')

        _ensure_index(
            'ix_tienda_promociones_cliente_estado_fecha',
            'CREATE INDEX ix_tienda_promociones_cliente_estado_fecha ON tienda_promociones (id_cliente, activa, fecha_inicio, fecha_fin)',
        )
        _ensure_index(
            'ix_tienda_promocion_productos_producto_promocion',
            'CREATE INDEX ix_tienda_promocion_productos_producto_promocion ON tienda_promocion_productos (id_producto, id_promocion)',
        )

        db.session.commit()
        print('Migración de promociones de tienda completada.')


if __name__ == '__main__':
    run_migration()
