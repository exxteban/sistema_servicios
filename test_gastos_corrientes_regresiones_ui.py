import tempfile
import unittest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text

from app import create_app, db
from gastos_corrientes.schema import ensure_gastos_corrientes_schema


class TestGastosCorrientesRegresionesUI(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.app.config['PROJECT_ROOT'] = self.tempdir.name
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Usuario

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin.id_usuario)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        self.tempdir.cleanup()

    def _login_como(self, usuario):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(usuario.id_usuario)
            session['_fresh'] = True

    def _crear_usuario_con_permisos(self, username, permisos):
        from app.models import Permiso, Rol, Usuario

        rol = Rol(
            nombre=f'Rol {username}',
            descripcion='Rol de pruebas para gastos corrientes',
            nivel_jerarquia=50,
            activo=True,
        )
        db.session.add(rol)
        db.session.flush()
        for permiso in Permiso.query.filter(Permiso.codigo.in_(permisos)).all():
            rol.permisos.append(permiso)

        usuario = Usuario(
            username=username,
            nombre_completo=username,
            id_rol=rol.id_rol,
            activo=True,
        )
        usuario.set_password('test123')
        db.session.add(usuario)
        db.session.commit()
        return usuario

    def _crear_gasto(self, nombre='Internet Fibra', *, dia_vencimiento=12, fecha_creacion=None):
        from gastos_corrientes.models import GastoCorriente

        gasto = GastoCorriente(
            nombre=nombre,
            categoria='internet',
            monto_estimado=Decimal('250000.00'),
            dia_vencimiento=dia_vencimiento,
            activo=True,
            requiere_caja_por_defecto=True,
            alerta_activa=True,
            dias_anticipacion_alerta=3,
            fecha_creacion=fecha_creacion or datetime(2026, 4, 1, 9, 0, 0),
        )
        db.session.add(gasto)
        db.session.commit()
        return gasto

    def test_formulario_gasto_expone_requiere_caja_por_defecto(self):
        response = self.client.get('/gastos-corrientes/nuevo')

        self.assertEqual(response.status_code, 200)
        self.assertIn('name="requiere_caja_por_defecto"', response.get_data(as_text=True))

    def test_detalle_preserva_periodo_en_boton_registrar_pago(self):
        gasto = self._crear_gasto('Luz')

        response = self.client.get(f'/gastos-corrientes/{gasto.id_gasto_corriente}?periodo=2026-04')

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo?periodo=2026-04',
            response.get_data(as_text=True),
        )

    def test_listado_muestra_boton_eliminar_gasto(self):
        gasto = self._crear_gasto('Sistema')

        response = self.client.get('/gastos-corrientes/?periodo=2026-04')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'/gastos-corrientes/{gasto.id_gasto_corriente}/eliminar', html)
        self.assertIn('Eliminar', html)

    def test_detalle_expone_formulario_para_sincronizar_periodo_actual(self):
        gasto = self._crear_gasto('Agua')

        response = self.client.get(
            f'/gastos-corrientes/{gasto.id_gasto_corriente}?periodo=2026-04&categoria=internet&estado=pendiente'
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('/gastos-corrientes/sincronizar-periodo', html)
        self.assertIn('name="periodo" value="2026-04"', html)
        self.assertIn('name="categoria" value="internet"', html)
        self.assertIn('name="estado" value="pendiente"', html)
        self.assertIn('Sincronizar período', html)

    def test_listado_pagado_muestra_ver_pago_para_usuario_solo_lectura(self):
        from gastos_corrientes.models import PagoGastoCorriente

        gasto = self._crear_gasto('Internet')
        self.client.post(
            f'/gastos-corrientes/pago/{gasto.id_gasto_corriente}/nuevo',
            data={
                'periodo': '2026-04',
                'fecha_pago': '2026-04-10',
                'monto_pagado': '250000',
            },
            follow_redirects=False,
        )
        pago = PagoGastoCorriente.query.filter_by(id_gasto_corriente=gasto.id_gasto_corriente).first()
        self.assertIsNotNone(pago)

        usuario = self._crear_usuario_con_permisos('gc_lector_pago', ['ver_gastos_corrientes'])
        self._login_como(usuario)

        response = self.client.get('/gastos-corrientes/?periodo=2026-04')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Ver pago', html)
        self.assertIn(f'/gastos-corrientes/pago/{pago.id_pago_gasto_corriente}', html)

    def test_ensure_schema_agrega_columnas_compatibilidad_en_sqlite(self):
        self.assertEqual(db.engine.dialect.name, 'sqlite')

        db.session.execute(text('DROP TABLE IF EXISTS pagos_gastos_corrientes'))
        db.session.execute(text('DROP TABLE IF EXISTS gastos_corrientes'))
        db.session.execute(text(
            """
            CREATE TABLE gastos_corrientes (
                id_gasto_corriente INTEGER PRIMARY KEY,
                cliente_id INTEGER,
                nombre VARCHAR(120) NOT NULL,
                categoria VARCHAR(30) NOT NULL DEFAULT 'otros',
                descripcion TEXT,
                monto_estimado NUMERIC(12, 2) NOT NULL DEFAULT 0,
                dia_vencimiento INTEGER NOT NULL DEFAULT 1,
                activo BOOLEAN NOT NULL DEFAULT 1,
                fecha_creacion DATETIME,
                fecha_actualizacion DATETIME
            )
            """
        ))
        db.session.execute(text(
            """
            CREATE TABLE pagos_gastos_corrientes (
                id_pago_gasto_corriente INTEGER PRIMARY KEY,
                cliente_id INTEGER,
                id_gasto_corriente INTEGER NOT NULL,
                periodo_anio INTEGER NOT NULL,
                periodo_mes INTEGER NOT NULL,
                fecha_vencimiento DATE NOT NULL,
                fecha_pago DATE,
                monto_estimado NUMERIC(12, 2) NOT NULL DEFAULT 0,
                monto_pagado NUMERIC(12, 2) NOT NULL DEFAULT 0,
                estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
                pagado_desde_caja BOOLEAN NOT NULL DEFAULT 0,
                observacion TEXT,
                fecha_creacion DATETIME,
                fecha_actualizacion DATETIME
            )
            """
        ))
        db.session.commit()

        ensure_gastos_corrientes_schema()

        columnas_gastos = {
            row[1] for row in db.session.execute(text('PRAGMA table_info(gastos_corrientes)')).fetchall()
        }
        columnas_pagos = {
            row[1] for row in db.session.execute(text('PRAGMA table_info(pagos_gastos_corrientes)')).fetchall()
        }

        self.assertIn('requiere_caja_por_defecto', columnas_gastos)
        self.assertIn('alerta_activa', columnas_gastos)
        self.assertIn('dias_anticipacion_alerta', columnas_gastos)
        self.assertIn('numero_comprobante', columnas_pagos)
        self.assertIn('id_movimiento_reversa', columnas_pagos)
        self.assertIn('motivo_anulacion', columnas_pagos)
        self.assertIn('fecha_anulacion', columnas_pagos)


if __name__ == '__main__':
    unittest.main()
