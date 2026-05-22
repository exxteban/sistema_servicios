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


def _mysql_table_exists(table_name: str) -> bool:
    return bool(db.session.execute(text("""
        SELECT COUNT(*) FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :table_name
    """), {'table_name': table_name}).scalar())


def _mysql_column_exists(table_name: str, column_name: str) -> bool:
    return bool(db.session.execute(text("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :table_name
          AND COLUMN_NAME = :column_name
    """), {'table_name': table_name, 'column_name': column_name}).scalar())


def _mysql_index_exists(table_name: str, index_name: str) -> bool:
    return bool(db.session.execute(text("""
        SELECT COUNT(*) FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :table_name
          AND INDEX_NAME = :index_name
    """), {'table_name': table_name, 'index_name': index_name}).scalar())


def _mysql_fk_exists(table_name: str, fk_name: str) -> bool:
    return bool(db.session.execute(text("""
        SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :table_name
          AND CONSTRAINT_NAME = :fk_name
          AND CONSTRAINT_TYPE = 'FOREIGN KEY'
    """), {'table_name': table_name, 'fk_name': fk_name}).scalar())


def _sqlite_table_exists(table_name: str) -> bool:
    return bool(db.session.execute(text("""
        SELECT COUNT(*) FROM sqlite_master
        WHERE type = 'table' AND name = :table_name
    """), {'table_name': table_name}).scalar())


def _sqlite_columns(table_name: str):
    if not _sqlite_table_exists(table_name):
        return []
    return [row[1] for row in db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()]


def run_migration():
    with app.app_context():
        dialect = db.engine.dialect.name

        if dialect == 'mysql':
            _mysql_migrate_servicios()
            _mysql_migrate_detalle_ventas()
            db.session.commit()
            return

        if dialect == 'sqlite':
            _sqlite_migrate_servicios()
            _sqlite_migrate_detalle_ventas()
            db.session.commit()
            return

        raise RuntimeError(f'Dialecto no soportado para esta migracion: {dialect}')


def _mysql_migrate_servicios():
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS servicios (
            id_servicio INT AUTO_INCREMENT PRIMARY KEY,
            codigo VARCHAR(50) NULL,
            nombre VARCHAR(200) NOT NULL,
            categoria VARCHAR(100) NULL,
            descripcion TEXT NULL,
            costo NUMERIC(10, 2) NOT NULL DEFAULT 0,
            precio NUMERIC(10, 2) NOT NULL,
            duracion_minutos INT NOT NULL DEFAULT 30,
            porcentaje_iva INT NOT NULL DEFAULT 10,
            activo TINYINT(1) NOT NULL DEFAULT 1,
            turno_rapido_tipo VARCHAR(30) NULL,
            publicado_tienda TINYINT(1) NOT NULL DEFAULT 0,
            descripcion_tienda TEXT NULL,
            orden_tienda INT NOT NULL DEFAULT 0,
            fecha_creacion DATETIME NULL,
            fecha_modificacion DATETIME NULL,
            id_usuario_modificacion INT NULL,
            INDEX ix_servicios_codigo (codigo),
            INDEX ix_servicios_activo (activo),
            INDEX ix_servicios_turno_rapido_tipo (turno_rapido_tipo),
            INDEX ix_servicios_publicado (publicado_tienda, activo),
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

    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS cliente_servicios (
            id_cliente_servicio INT AUTO_INCREMENT PRIMARY KEY,
            id_cliente INT NOT NULL,
            id_servicio INT NOT NULL,
            cantidad INT NOT NULL DEFAULT 1,
            costo_pactado NUMERIC(10, 2) NOT NULL DEFAULT 0,
            precio_pactado NUMERIC(10, 2) NOT NULL,
            estado VARCHAR(20) NOT NULL DEFAULT 'solicitado',
            fecha_solicitud DATETIME NOT NULL,
            fecha_programada DATETIME NULL,
            fecha_cierre DATETIME NULL,
            observaciones TEXT NULL,
            id_venta INT NULL,
            id_usuario_registro INT NULL,
            INDEX ix_cliente_servicios_cliente_estado (id_cliente, estado),
            INDEX ix_cliente_servicios_servicio_estado (id_servicio, estado),
            INDEX ix_cliente_servicios_fecha (fecha_solicitud),
            CONSTRAINT fk_cliente_servicios_cliente FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
            CONSTRAINT fk_cliente_servicios_servicio FOREIGN KEY (id_servicio) REFERENCES servicios(id_servicio) ON DELETE RESTRICT,
            CONSTRAINT fk_cliente_servicios_venta FOREIGN KEY (id_venta) REFERENCES ventas(id_venta) ON DELETE SET NULL,
            CONSTRAINT fk_cliente_servicios_usuario FOREIGN KEY (id_usuario_registro) REFERENCES usuarios(id_usuario) ON DELETE SET NULL
        )
    """))
    if not _mysql_column_exists('cliente_servicios', 'id_venta'):
        db.session.execute(text("ALTER TABLE cliente_servicios ADD COLUMN id_venta INT NULL"))
    if not _mysql_index_exists('cliente_servicios', 'ix_cliente_servicios_id_venta'):
        db.session.execute(text("CREATE INDEX ix_cliente_servicios_id_venta ON cliente_servicios(id_venta)"))
    if not _mysql_fk_exists('cliente_servicios', 'fk_cliente_servicios_venta'):
        db.session.execute(text("""
            ALTER TABLE cliente_servicios
            ADD CONSTRAINT fk_cliente_servicios_venta
            FOREIGN KEY (id_venta) REFERENCES ventas(id_venta) ON DELETE SET NULL
        """))

    if _mysql_column_exists('servicios', 'id_cliente'):
        db.session.execute(text("""
            INSERT INTO cliente_servicios (
                id_cliente,
                id_servicio,
                cantidad,
                costo_pactado,
                precio_pactado,
                estado,
                fecha_solicitud,
                fecha_programada,
                fecha_cierre,
                observaciones,
                id_venta,
                id_usuario_registro
            )
            SELECT
                s.id_cliente,
                s.id_servicio,
                1,
                COALESCE(s.costo, 0),
                COALESCE(s.precio, 0),
                'migrado',
                COALESCE(s.fecha_creacion, NOW()),
                NULL,
                NULL,
                'Migrado desde la relación legacy servicio-cliente.',
                NULL,
                s.id_usuario_modificacion
            FROM servicios s
            WHERE s.id_cliente IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM cliente_servicios cs
                  WHERE cs.id_cliente = s.id_cliente
                    AND cs.id_servicio = s.id_servicio
                    AND cs.estado = 'migrado'
              )
        """))

        if _mysql_fk_exists('servicios', 'fk_servicios_cliente'):
            db.session.execute(text("ALTER TABLE servicios DROP FOREIGN KEY fk_servicios_cliente"))
        if _mysql_index_exists('servicios', 'uq_servicios_cliente_codigo'):
            db.session.execute(text("ALTER TABLE servicios DROP INDEX uq_servicios_cliente_codigo"))
        if _mysql_index_exists('servicios', 'ix_servicios_cliente_activo'):
            db.session.execute(text("ALTER TABLE servicios DROP INDEX ix_servicios_cliente_activo"))
        if _mysql_index_exists('servicios', 'ix_servicios_cliente_publicado'):
            db.session.execute(text("ALTER TABLE servicios DROP INDEX ix_servicios_cliente_publicado"))
        db.session.execute(text("ALTER TABLE servicios DROP COLUMN id_cliente"))

    if not _mysql_index_exists('servicios', 'ix_servicios_codigo'):
        db.session.execute(text("CREATE INDEX ix_servicios_codigo ON servicios(codigo)"))
    if not _mysql_index_exists('servicios', 'ix_servicios_activo'):
        db.session.execute(text("CREATE INDEX ix_servicios_activo ON servicios(activo)"))
    if not _mysql_column_exists('servicios', 'turno_rapido_tipo'):
        db.session.execute(text("ALTER TABLE servicios ADD COLUMN turno_rapido_tipo VARCHAR(30) NULL"))
    if not _mysql_index_exists('servicios', 'ix_servicios_turno_rapido_tipo'):
        db.session.execute(text("CREATE INDEX ix_servicios_turno_rapido_tipo ON servicios(turno_rapido_tipo)"))
    if not _mysql_index_exists('servicios', 'ix_servicios_publicado'):
        db.session.execute(text("CREATE INDEX ix_servicios_publicado ON servicios(publicado_tienda, activo)"))


def _mysql_migrate_detalle_ventas():
    if not _mysql_table_exists('detalle_ventas'):
        return
    if not _mysql_column_exists('detalle_ventas', 'id_servicio'):
        db.session.execute(text("ALTER TABLE detalle_ventas ADD COLUMN id_servicio INT NULL"))
    if not _mysql_index_exists('detalle_ventas', 'ix_detalle_ventas_id_servicio'):
        db.session.execute(text("CREATE INDEX ix_detalle_ventas_id_servicio ON detalle_ventas(id_servicio)"))
    if not _mysql_fk_exists('detalle_ventas', 'fk_detalle_ventas_servicio'):
        db.session.execute(text("""
            ALTER TABLE detalle_ventas
            ADD CONSTRAINT fk_detalle_ventas_servicio
            FOREIGN KEY (id_servicio) REFERENCES servicios(id_servicio) ON DELETE SET NULL
        """))
    db.session.execute(text("ALTER TABLE detalle_ventas MODIFY id_producto INT NULL"))


def _sqlite_create_servicios_table(table_name='servicios'):
    db.session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id_servicio INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo VARCHAR(50),
            nombre VARCHAR(200) NOT NULL,
            categoria VARCHAR(100),
            descripcion TEXT,
            costo NUMERIC(10, 2) NOT NULL DEFAULT 0,
            precio NUMERIC(10, 2) NOT NULL,
            duracion_minutos INTEGER NOT NULL DEFAULT 30,
            porcentaje_iva INTEGER NOT NULL DEFAULT 10,
            activo BOOLEAN NOT NULL DEFAULT 1,
            turno_rapido_tipo VARCHAR(30),
            publicado_tienda BOOLEAN NOT NULL DEFAULT 0,
            descripcion_tienda TEXT,
            orden_tienda INTEGER NOT NULL DEFAULT 0,
            fecha_creacion DATETIME,
            fecha_modificacion DATETIME,
            id_usuario_modificacion INTEGER,
            FOREIGN KEY(id_usuario_modificacion) REFERENCES usuarios(id_usuario) ON DELETE SET NULL
        )
    """))


def _sqlite_create_servicio_precios_opciones():
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


def _sqlite_create_cliente_servicios():
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS cliente_servicios (
            id_cliente_servicio INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cliente INTEGER NOT NULL,
            id_servicio INTEGER NOT NULL,
            cantidad INTEGER NOT NULL DEFAULT 1,
            costo_pactado NUMERIC(10, 2) NOT NULL DEFAULT 0,
            precio_pactado NUMERIC(10, 2) NOT NULL,
            estado VARCHAR(20) NOT NULL DEFAULT 'solicitado',
            fecha_solicitud DATETIME NOT NULL,
            fecha_programada DATETIME,
            fecha_cierre DATETIME,
            observaciones TEXT,
            id_venta INTEGER,
            id_usuario_registro INTEGER,
            FOREIGN KEY(id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
            FOREIGN KEY(id_servicio) REFERENCES servicios(id_servicio) ON DELETE RESTRICT,
            FOREIGN KEY(id_venta) REFERENCES ventas(id_venta) ON DELETE SET NULL,
            FOREIGN KEY(id_usuario_registro) REFERENCES usuarios(id_usuario) ON DELETE SET NULL
        )
    """))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_cliente_servicios_cliente_estado ON cliente_servicios(id_cliente, estado)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_cliente_servicios_servicio_estado ON cliente_servicios(id_servicio, estado)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_cliente_servicios_fecha ON cliente_servicios(fecha_solicitud)"))


def _sqlite_migrate_servicios():
    cols = _sqlite_columns('servicios')
    _sqlite_create_cliente_servicios()
    cliente_servicios_cols = _sqlite_columns('cliente_servicios')
    if 'id_venta' not in cliente_servicios_cols:
        db.session.execute(text("ALTER TABLE cliente_servicios ADD COLUMN id_venta INTEGER"))
        cliente_servicios_cols = _sqlite_columns('cliente_servicios')
    if 'id_venta' in cliente_servicios_cols:
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_cliente_servicios_id_venta ON cliente_servicios(id_venta)"))

    if not cols:
        _sqlite_create_servicios_table()
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_servicios_codigo ON servicios(codigo)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_servicios_activo ON servicios(activo)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_servicios_turno_rapido_tipo ON servicios(turno_rapido_tipo)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_servicios_publicado ON servicios(publicado_tienda, activo)"))
        _sqlite_create_servicio_precios_opciones()
        return

    if 'id_cliente' in cols:
        db.session.execute(text("PRAGMA foreign_keys=OFF"))
        _sqlite_create_servicios_table('servicios_new')
        db.session.execute(text("""
            INSERT INTO servicios_new (
                id_servicio,
                codigo,
                nombre,
                categoria,
                descripcion,
                costo,
                precio,
                duracion_minutos,
                porcentaje_iva,
                activo,
                turno_rapido_tipo,
                publicado_tienda,
                descripcion_tienda,
                orden_tienda,
                fecha_creacion,
                fecha_modificacion,
                id_usuario_modificacion
            )
            SELECT
                id_servicio,
                codigo,
                nombre,
                categoria,
                descripcion,
                costo,
                precio,
                duracion_minutos,
                porcentaje_iva,
                activo,
                NULL,
                publicado_tienda,
                descripcion_tienda,
                orden_tienda,
                fecha_creacion,
                fecha_modificacion,
                id_usuario_modificacion
            FROM servicios
        """))
        db.session.execute(text("""
            INSERT INTO cliente_servicios (
                id_cliente,
                id_servicio,
                cantidad,
                costo_pactado,
                precio_pactado,
                estado,
                fecha_solicitud,
                fecha_programada,
                fecha_cierre,
                observaciones,
                id_venta,
                id_usuario_registro
            )
            SELECT
                id_cliente,
                id_servicio,
                1,
                COALESCE(costo, 0),
                COALESCE(precio, 0),
                'migrado',
                COALESCE(fecha_creacion, CURRENT_TIMESTAMP),
                NULL,
                NULL,
                'Migrado desde la relación legacy servicio-cliente.',
                NULL,
                id_usuario_modificacion
            FROM servicios
            WHERE id_cliente IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM cliente_servicios cs
                  WHERE cs.id_cliente = servicios.id_cliente
                    AND cs.id_servicio = servicios.id_servicio
                    AND cs.estado = 'migrado'
              )
        """))
        db.session.execute(text("DROP TABLE servicios"))
        db.session.execute(text("ALTER TABLE servicios_new RENAME TO servicios"))
        db.session.execute(text("PRAGMA foreign_keys=ON"))

    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_servicios_codigo ON servicios(codigo)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_servicios_activo ON servicios(activo)"))
    if 'turno_rapido_tipo' not in _sqlite_columns('servicios'):
        db.session.execute(text("ALTER TABLE servicios ADD COLUMN turno_rapido_tipo VARCHAR(30)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_servicios_turno_rapido_tipo ON servicios(turno_rapido_tipo)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_servicios_publicado ON servicios(publicado_tienda, activo)"))
    _sqlite_create_servicio_precios_opciones()


def _sqlite_migrate_detalle_ventas():
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
