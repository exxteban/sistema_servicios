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


def _mysql_column_exists(table_name: str, column_name: str) -> bool:
    return bool(db.session.execute(text("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :table_name
          AND COLUMN_NAME = :column_name
    """), {'table_name': table_name, 'column_name': column_name}).scalar())


def run_migration():
    with app.app_context():
        dialect = db.engine.dialect.name

        if dialect == 'mysql':
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS servicios (
                    id_servicio INT AUTO_INCREMENT PRIMARY KEY,
                    id_cliente INT NOT NULL,
                    codigo VARCHAR(50) NULL,
                    nombre VARCHAR(200) NOT NULL,
                    categoria VARCHAR(100) NULL,
                    descripcion TEXT NULL,
                    costo NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    precio NUMERIC(10, 2) NOT NULL,
                    duracion_minutos INT NOT NULL DEFAULT 30,
                    porcentaje_iva INT NOT NULL DEFAULT 10,
                    activo TINYINT(1) NOT NULL DEFAULT 1,
                    publicado_tienda TINYINT(1) NOT NULL DEFAULT 0,
                    descripcion_tienda TEXT NULL,
                    orden_tienda INT NOT NULL DEFAULT 0,
                    fecha_creacion DATETIME NULL,
                    fecha_modificacion DATETIME NULL,
                    id_usuario_modificacion INT NULL,
                    UNIQUE KEY uq_servicios_cliente_codigo (id_cliente, codigo),
                    INDEX ix_servicios_cliente_activo (id_cliente, activo),
                    INDEX ix_servicios_cliente_publicado (id_cliente, publicado_tienda, activo),
                    CONSTRAINT fk_servicios_cliente FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
                    CONSTRAINT fk_servicios_usuario_mod FOREIGN KEY (id_usuario_modificacion) REFERENCES usuarios(id_usuario) ON DELETE SET NULL
                )
            """))
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS servicio_precios_opciones (
                    id_opcion_precio INT AUTO_INCREMENT PRIMARY KEY,
                    id_servicio INT NOT NULL,
                    etiqueta VARCHAR(100) NOT NULL,
                    costo NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    precio NUMERIC(10, 2) NOT NULL,
                    orden INT NOT NULL DEFAULT 0,
                    activo TINYINT(1) NOT NULL DEFAULT 1,
                    fecha_creacion DATETIME NULL,
                    INDEX ix_servicio_precios_opciones_servicio_activo (id_servicio, activo),
                    CONSTRAINT fk_servicio_precios_opciones_servicio FOREIGN KEY (id_servicio) REFERENCES servicios(id_servicio) ON DELETE CASCADE
                )
            """))
            if not _mysql_column_exists('detalle_ventas', 'id_servicio'):
                db.session.execute(text("ALTER TABLE detalle_ventas ADD COLUMN id_servicio INT NULL"))
                db.session.execute(text("CREATE INDEX ix_detalle_ventas_id_servicio ON detalle_ventas(id_servicio)"))
                db.session.execute(text("""
                    ALTER TABLE detalle_ventas
                    ADD CONSTRAINT fk_detalle_ventas_servicio
                    FOREIGN KEY (id_servicio) REFERENCES servicios(id_servicio) ON DELETE SET NULL
                """))
            db.session.execute(text("ALTER TABLE detalle_ventas MODIFY id_producto INT NULL"))
            db.session.commit()
            return

        if dialect == 'sqlite':
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS servicios (
                    id_servicio INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_cliente INTEGER NOT NULL,
                    codigo VARCHAR(50),
                    nombre VARCHAR(200) NOT NULL,
                    categoria VARCHAR(100),
                    descripcion TEXT,
                    costo NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    precio NUMERIC(10, 2) NOT NULL,
                    duracion_minutos INTEGER NOT NULL DEFAULT 30,
                    porcentaje_iva INTEGER NOT NULL DEFAULT 10,
                    activo BOOLEAN NOT NULL DEFAULT 1,
                    publicado_tienda BOOLEAN NOT NULL DEFAULT 0,
                    descripcion_tienda TEXT,
                    orden_tienda INTEGER NOT NULL DEFAULT 0,
                    fecha_creacion DATETIME,
                    fecha_modificacion DATETIME,
                    id_usuario_modificacion INTEGER,
                    FOREIGN KEY(id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
                    FOREIGN KEY(id_usuario_modificacion) REFERENCES usuarios(id_usuario) ON DELETE SET NULL,
                    UNIQUE(id_cliente, codigo)
                )
            """))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_servicios_cliente_activo ON servicios(id_cliente, activo)"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_servicios_cliente_publicado ON servicios(id_cliente, publicado_tienda, activo)"))
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS servicio_precios_opciones (
                    id_opcion_precio INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_servicio INTEGER NOT NULL,
                    etiqueta VARCHAR(100) NOT NULL,
                    costo NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    precio NUMERIC(10, 2) NOT NULL,
                    orden INTEGER NOT NULL DEFAULT 0,
                    activo BOOLEAN NOT NULL DEFAULT 1,
                    fecha_creacion DATETIME,
                    FOREIGN KEY(id_servicio) REFERENCES servicios(id_servicio) ON DELETE CASCADE
                )
            """))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_servicio_precios_opciones_servicio_activo ON servicio_precios_opciones(id_servicio, activo)"))
            _migrar_detalle_ventas_sqlite()
            db.session.commit()
            return

        raise RuntimeError(f'Dialecto no soportado para esta migracion: {dialect}')


def _migrar_detalle_ventas_sqlite():
    cols = db.session.execute(text("PRAGMA table_info(detalle_ventas)")).fetchall()
    if not cols:
        return
    col_names = [row[1] for row in cols]
    id_producto_col = next((row for row in cols if row[1] == 'id_producto'), None)
    needs_rebuild = bool(id_producto_col and int(id_producto_col[3] or 0) == 1)

    if 'id_servicio' not in col_names and not needs_rebuild:
        db.session.execute(text("ALTER TABLE detalle_ventas ADD COLUMN id_servicio INTEGER"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_detalle_ventas_id_servicio ON detalle_ventas(id_servicio)"))
        return
    if 'id_servicio' in col_names and not needs_rebuild:
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_detalle_ventas_id_servicio ON detalle_ventas(id_servicio)"))
        return

    db.session.execute(text("PRAGMA foreign_keys=OFF"))
    db.session.execute(text("""
        CREATE TABLE detalle_ventas_new (
            id_detalle_venta INTEGER PRIMARY KEY AUTOINCREMENT,
            id_venta INTEGER NOT NULL,
            id_producto INTEGER,
            id_servicio INTEGER,
            cantidad INTEGER NOT NULL,
            precio_unitario NUMERIC(15, 2) NOT NULL,
            precio_original NUMERIC(15, 2) NOT NULL,
            porcentaje_iva INTEGER NOT NULL,
            monto_iva NUMERIC(15, 2) NOT NULL,
            descuento_linea NUMERIC(15, 2) DEFAULT 0,
            subtotal NUMERIC(15, 2) NOT NULL,
            es_kit BOOLEAN DEFAULT 0,
            FOREIGN KEY(id_venta) REFERENCES ventas(id_venta) ON DELETE CASCADE,
            FOREIGN KEY(id_producto) REFERENCES productos(id_producto),
            FOREIGN KEY(id_servicio) REFERENCES servicios(id_servicio) ON DELETE SET NULL
        )
    """))
    select_id_servicio = 'id_servicio' if 'id_servicio' in col_names else 'NULL'
    db.session.execute(text(f"""
        INSERT INTO detalle_ventas_new (
            id_detalle_venta, id_venta, id_producto, id_servicio, cantidad,
            precio_unitario, precio_original, porcentaje_iva, monto_iva,
            descuento_linea, subtotal, es_kit
        )
        SELECT id_detalle_venta, id_venta, id_producto, {select_id_servicio}, cantidad,
               precio_unitario, precio_original, porcentaje_iva, monto_iva,
               descuento_linea, subtotal, es_kit
        FROM detalle_ventas
    """))
    db.session.execute(text("DROP TABLE detalle_ventas"))
    db.session.execute(text("ALTER TABLE detalle_ventas_new RENAME TO detalle_ventas"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_detalle_ventas_id_venta ON detalle_ventas(id_venta)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_detalle_ventas_id_producto ON detalle_ventas(id_producto)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_detalle_ventas_id_servicio ON detalle_ventas(id_servicio)"))
    db.session.execute(text("PRAGMA foreign_keys=ON"))


if __name__ == '__main__':
    run_migration()
