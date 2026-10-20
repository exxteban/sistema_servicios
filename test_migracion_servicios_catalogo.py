"""migrations/servicios_catalogo.py no tiene que perder columnas ni índices agregados después (SQLite)."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
MIGRACION = BASE_DIR / 'migrations' / 'servicios_catalogo.py'


class TestMigracionServiciosCatalogo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / 'vieja.db'

    def tearDown(self):
        self.tmp.cleanup()

    def _sql(self, script):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.executescript(script)
            conn.commit()

    def _query(self, sql):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return conn.execute(sql).fetchall()

    def _columnas(self, tabla):
        return {row[1]: row for row in self._query(f'PRAGMA table_info({tabla})')}

    def _indices(self, tabla):
        return {row[1] for row in self._query(f'PRAGMA index_list({tabla})')}

    def _migrar(self):
        env = dict(os.environ, DATABASE_URL=f'sqlite:///{self.db_path.as_posix()}')
        resultado = subprocess.run(
            [sys.executable, str(MIGRACION)], cwd=BASE_DIR, env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_detalle_ventas_conserva_columnas_de_promociones(self):
        self._sql("""
            CREATE TABLE detalle_ventas (
                id_detalle_venta INTEGER PRIMARY KEY AUTOINCREMENT,
                id_venta INTEGER NOT NULL,
                id_producto INTEGER NOT NULL,
                cantidad INTEGER NOT NULL,
                precio_unitario NUMERIC(15, 2) NOT NULL,
                precio_original NUMERIC(15, 2) NOT NULL,
                porcentaje_iva INTEGER NOT NULL,
                monto_iva NUMERIC(15, 2) NOT NULL,
                descuento_linea NUMERIC(15, 2) DEFAULT 0,
                subtotal NUMERIC(15, 2) NOT NULL,
                es_kit BOOLEAN DEFAULT 0
            );
            ALTER TABLE detalle_ventas ADD COLUMN id_promocion_aplicada INTEGER NULL;
            ALTER TABLE detalle_ventas ADD COLUMN promocion_descripcion VARCHAR(255) NULL;
            ALTER TABLE detalle_ventas ADD COLUMN cantidad_bonificada INTEGER NOT NULL DEFAULT 0;
            CREATE INDEX ix_detalle_ventas_promocion ON detalle_ventas(id_promocion_aplicada);
            INSERT INTO detalle_ventas (
                id_venta, id_producto, cantidad, precio_unitario, precio_original, porcentaje_iva,
                monto_iva, subtotal, id_promocion_aplicada, promocion_descripcion, cantidad_bonificada
            ) VALUES (1, 5, 3, 1000, 1000, 10, 273, 3000, 9, '3x2', 1);
        """)

        self._migrar()

        columnas = self._columnas('detalle_ventas')
        self.assertEqual(columnas['id_producto'][3], 0)
        self.assertIn('id_servicio', columnas)
        self.assertEqual(columnas['cantidad_bonificada'][3], 1)
        self.assertIn('ix_detalle_ventas_promocion', self._indices('detalle_ventas'))
        self.assertEqual(
            self._query('SELECT id_producto, id_servicio, id_promocion_aplicada, promocion_descripcion, cantidad_bonificada FROM detalle_ventas'),
            [(5, None, 9, '3x2', 1)],
        )

        self._migrar()
        self.assertEqual(self._query('SELECT COUNT(*) FROM detalle_ventas'), [(1,)])

    def test_servicios_legacy_conserva_columnas_extra_y_quita_id_cliente(self):
        self._sql("""
            CREATE TABLE servicios (
                id_servicio INTEGER PRIMARY KEY AUTOINCREMENT,
                id_cliente INTEGER,
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
                color_agenda VARCHAR(20) DEFAULT 'azul'
            );
            CREATE INDEX ix_servicios_id_cliente ON servicios(id_cliente);
            CREATE INDEX ix_servicios_color ON servicios(color_agenda);
            INSERT INTO servicios (id_cliente, nombre, precio, turno_rapido_tipo, color_agenda)
            VALUES (4, 'Corte', 50000, 'corte', 'rojo');
        """)

        self._migrar()

        columnas = self._columnas('servicios')
        self.assertNotIn('id_cliente', columnas)
        indices = self._indices('servicios')
        self.assertNotIn('ix_servicios_id_cliente', indices)
        self.assertIn('ix_servicios_color', indices)
        self.assertEqual(
            self._query('SELECT nombre, turno_rapido_tipo, color_agenda FROM servicios'),
            [('Corte', 'corte', 'rojo')],
        )
        self.assertEqual(
            self._query('SELECT id_cliente, id_servicio, estado FROM cliente_servicios'),
            [(4, 1, 'migrado')],
        )


if __name__ == '__main__':
    unittest.main()
