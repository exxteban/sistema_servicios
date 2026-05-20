import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from app import create_app, db
from app.models import Usuario
from app.utils.init_db import inicializar_datos_base
from gastos_corrientes.models import GastoCorriente, PagoGastoCorriente
from gastos_corrientes.services import (
    construir_panel_gastos_corrientes,
    obtener_dashboard_detallado_gastos_corrientes,
    obtener_recordatorios_gastos_corrientes,
    obtener_resumen_dashboard_gastos_corrientes,
)


class _FakeAdminUser:
    id_usuario = 1
    id_cliente = None

    def es_admin(self):
        return True

    def tiene_permiso(self, _permiso):
        return True


class _FakeTenantUser:
    id_usuario = 2

    def __init__(self, cliente_id):
        self.id_cliente = cliente_id

    def es_admin(self):
        return False

    def tiene_permiso(self, _permiso):
        return True


class TestDashboardGastosCorrientesResumen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        cls.ctx.pop()

    def setUp(self):
        db.session.remove()
        db.drop_all()
        db.create_all()
        inicializar_datos_base(config_name='testing')
        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin.id_usuario)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()

    def _crear_gasto(
        self,
        *,
        nombre,
        monto,
        dia_vencimiento,
        categoria='servicios',
        alerta_activa=True,
        dias_anticipacion_alerta=3,
        cliente_id=None,
        activo=True,
        fecha_creacion=None,
    ):
        gasto = GastoCorriente(
            cliente_id=cliente_id,
            nombre=nombre,
            categoria=categoria,
            monto_estimado=Decimal(monto),
            dia_vencimiento=dia_vencimiento,
            activo=activo,
            requiere_caja_por_defecto=True,
            alerta_activa=alerta_activa,
            dias_anticipacion_alerta=dias_anticipacion_alerta,
            fecha_creacion=fecha_creacion or datetime(2026, 4, 1, 9, 0, 0),
        )
        db.session.add(gasto)
        db.session.commit()
        return gasto

    def _crear_pago_pagado(self, gasto, *, periodo_anio, periodo_mes, fecha_pago, monto_pagado):
        pago = PagoGastoCorriente(
            cliente_id=gasto.cliente_id,
            id_gasto_corriente=gasto.id_gasto_corriente,
            periodo_anio=periodo_anio,
            periodo_mes=periodo_mes,
            fecha_vencimiento=date(periodo_anio, periodo_mes, gasto.dia_vencimiento_int()),
            fecha_pago=fecha_pago,
            monto_estimado=gasto.monto_estimado_decimal(),
            monto_pagado=Decimal(monto_pagado),
            estado='pagado',
            pagado_desde_caja=False,
        )
        db.session.add(pago)
        db.session.commit()
        return pago

    def test_resumen_dashboard_consolida_vencidos_alertas_y_pendiente(self):
        self._crear_gasto(nombre='Luz', monto='100000.00', dia_vencimiento=5)
        self._crear_gasto(nombre='Internet', monto='200000.00', dia_vencimiento=12, dias_anticipacion_alerta=3)
        self._crear_gasto(nombre='Alquiler', monto='300000.00', dia_vencimiento=25)
        self._crear_gasto(nombre='Impuesto sin alerta', monto='400000.00', dia_vencimiento=7, alerta_activa=False)
        gasto_pagado = self._crear_gasto(nombre='Limpieza pagada', monto='500000.00', dia_vencimiento=9)
        self._crear_pago_pagado(
            gasto_pagado,
            periodo_anio=2026,
            periodo_mes=4,
            fecha_pago=date(2026, 4, 9),
            monto_pagado='500000.00',
        )

        with patch('gastos_corrientes.services.gasto_corriente_service.current_user', _FakeAdminUser()):
            resumen = obtener_resumen_dashboard_gastos_corrientes(today=date(2026, 4, 10))

        self.assertEqual(resumen['periodo'], '2026-04')
        self.assertEqual(resumen['vencidos'], 2)
        self.assertEqual(resumen['por_vencer'], 1)
        self.assertEqual(resumen['pendientes'], 2)
        self.assertEqual(resumen['total_alertas'], 2)
        self.assertEqual(resumen['total_pendiente'], Decimal('1000000.00'))

    def test_resumen_dashboard_respeta_scope_cliente(self):
        self._crear_gasto(nombre='Cliente 1 vencido', monto='150000.00', dia_vencimiento=3, cliente_id=1)
        self._crear_gasto(nombre='Cliente 2 vencido', monto='250000.00', dia_vencimiento=4, cliente_id=2)

        with patch('gastos_corrientes.services.gasto_corriente_service.current_user', _FakeTenantUser(1)):
            resumen = obtener_resumen_dashboard_gastos_corrientes(today=date(2026, 4, 10))

        self.assertEqual(resumen['vencidos'], 1)
        self.assertEqual(resumen['total_alertas'], 1)
        self.assertEqual(resumen['total_pendiente'], Decimal('150000.00'))

    def test_recordatorios_gastos_corrientes_devuelven_alerta_y_vencido(self):
        self._crear_gasto(nombre='Luz', monto='100000.00', dia_vencimiento=5)
        self._crear_gasto(nombre='Internet', monto='200000.00', dia_vencimiento=12, dias_anticipacion_alerta=3)
        self._crear_gasto(nombre='Sin alerta', monto='300000.00', dia_vencimiento=4, alerta_activa=False)

        with patch('gastos_corrientes.services.gasto_corriente_service.current_user', _FakeAdminUser()):
            recordatorios = obtener_recordatorios_gastos_corrientes(today=date(2026, 4, 10), limit=10)

        self.assertEqual(recordatorios['count'], 2)
        self.assertEqual(recordatorios['overdue_count'], 1)
        self.assertEqual(recordatorios['alert_count'], 1)
        self.assertEqual([item['estado_alerta'] for item in recordatorios['items']], ['overdue', 'alert'])
        self.assertEqual(recordatorios['items'][0]['nombre'], 'Luz')
        self.assertEqual(recordatorios['items'][1]['nombre'], 'Internet')

    def test_panel_gastos_corrientes_incluye_comparativo_y_top_categorias(self):
        luz = self._crear_gasto(nombre='Luz', monto='100000.00', dia_vencimiento=5, categoria='servicios')
        internet = self._crear_gasto(nombre='Internet', monto='200000.00', dia_vencimiento=12, categoria='internet')
        alquiler = self._crear_gasto(nombre='Alquiler', monto='300000.00', dia_vencimiento=20, categoria='alquiler')

        self._crear_pago_pagado(
            luz,
            periodo_anio=2026,
            periodo_mes=4,
            fecha_pago=date(2026, 4, 5),
            monto_pagado='100000.00',
        )
        self._crear_pago_pagado(
            alquiler,
            periodo_anio=2026,
            periodo_mes=4,
            fecha_pago=date(2026, 4, 19),
            monto_pagado='330000.00',
        )

        with patch('gastos_corrientes.services.gasto_corriente_service.current_user', _FakeAdminUser()):
            with patch('gastos_corrientes.services.gasto_corriente_reporting.date') as mocked_date:
                mocked_date.today.return_value = date(2026, 4, 10)
                mocked_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
                panel = construir_panel_gastos_corrientes(periodo_raw='2026-04')

        self.assertEqual(panel['comparativo']['cantidad_items'], 3)
        self.assertEqual(panel['comparativo']['cantidad_pagados'], 2)
        self.assertEqual(panel['comparativo']['cantidad_pendientes'], 1)
        self.assertEqual(panel['comparativo']['porcentaje_pagado'], Decimal('71.67'))
        self.assertEqual(panel['comparativo']['porcentaje_pendiente'], Decimal('33.33'))
        self.assertEqual(panel['comparativo']['desviacion'], Decimal('-170000.00'))
        self.assertEqual(panel['categorias_resumen'][0]['categoria'], 'alquiler')
        self.assertEqual(panel['categorias_resumen'][0]['total_pagado'], Decimal('330000.00'))
        self.assertEqual(panel['categorias_resumen'][1]['categoria'], 'servicios')
        self.assertEqual(panel['categorias_resumen'][2]['categoria'], 'internet')

    def test_api_resumen_alertas_gastos_corrientes_retorna_json(self):
        self._crear_gasto(nombre='Luz', monto='100000.00', dia_vencimiento=5)
        self._crear_gasto(nombre='Internet', monto='200000.00', dia_vencimiento=12, dias_anticipacion_alerta=3)

        with patch('gastos_corrientes.services.gasto_corriente_reporting.date') as mocked_date:
            mocked_date.today.return_value = date(2026, 4, 10)
            mocked_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            response = self.client.get(
                '/gastos-corrientes/api/alertas/resumen?limit=10',
                headers={'Accept': 'application/json'},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload['count'], 2)
        self.assertEqual(payload['overdue_count'], 1)
        self.assertEqual(payload['alert_count'], 1)
        self.assertEqual(len(payload['items']), 2)

    def test_dashboard_detallado_gastos_corrientes_incluye_alertas_y_categorias_pendientes(self):
        luz = self._crear_gasto(nombre='Luz', monto='100000.00', dia_vencimiento=5, categoria='servicios')
        internet = self._crear_gasto(nombre='Internet', monto='200000.00', dia_vencimiento=12, categoria='internet')
        alquiler = self._crear_gasto(nombre='Alquiler', monto='300000.00', dia_vencimiento=20, categoria='alquiler')

        self._crear_pago_pagado(
            alquiler,
            periodo_anio=2026,
            periodo_mes=4,
            fecha_pago=date(2026, 4, 19),
            monto_pagado='330000.00',
        )

        with patch('gastos_corrientes.services.gasto_corriente_service.current_user', _FakeAdminUser()):
            resumen = obtener_dashboard_detallado_gastos_corrientes(today=date(2026, 4, 10))

        self.assertEqual(resumen['periodo'], '2026-04')
        self.assertEqual(resumen['vencidos'], 1)
        self.assertEqual(resumen['por_vencer'], 1)
        self.assertEqual(resumen['cantidad_pagados'], 1)
        self.assertEqual(resumen['cantidad_pendientes'], 2)
        self.assertEqual(len(resumen['items_urgentes']), 2)
        self.assertEqual(resumen['items_urgentes'][0]['nombre'], 'Luz')
        self.assertEqual(resumen['items_urgentes'][0]['estado_alerta'], 'overdue')
        self.assertEqual(resumen['categorias_pendientes'][0]['categoria'], 'internet')
        self.assertEqual(resumen['categorias_pendientes'][0]['total_pendiente'], Decimal('200000.00'))
        self.assertEqual(resumen['categorias_pendientes'][1]['categoria'], 'servicios')
        self.assertEqual(resumen['categorias_pendientes'][1]['total_pendiente'], Decimal('100000.00'))

    def test_dashboard_render_muestra_panel_avanzado_gastos_corrientes(self):
        self._crear_gasto(nombre='Luz', monto='100000.00', dia_vencimiento=5, categoria='servicios')
        self._crear_gasto(nombre='Internet', monto='200000.00', dia_vencimiento=12, categoria='internet')

        with patch('app.routes.main.today_local', return_value=date(2026, 4, 10)):
            response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Radar financiero', html)
        self.assertIn('Alertas prioritarias', html)
        self.assertIn('Categorías en foco', html)
        self.assertIn('Internet', html)

    def test_panel_gastos_corrientes_automatiza_pendientes_del_periodo(self):
        self._crear_gasto(nombre='Agua', monto='90000.00', dia_vencimiento=8, categoria='servicios')

        with patch('gastos_corrientes.services.gasto_corriente_service.current_user', _FakeAdminUser()):
            panel = construir_panel_gastos_corrientes(periodo_raw='2026-04')

        self.assertEqual(len(panel['items']), 1)
        self.assertEqual(panel['items'][0]['estado_panel'], 'vencido')
        self.assertEqual(PagoGastoCorriente.query.count(), 1)
        pago = PagoGastoCorriente.query.first()
        self.assertIsNotNone(pago)
        self.assertEqual(pago.estado, 'pendiente')

    def test_panel_gastos_corrientes_no_cuenta_en_fecha_como_alerta_activa(self):
        self._crear_gasto(nombre='Luz', monto='100000.00', dia_vencimiento=5, categoria='servicios')
        self._crear_gasto(nombre='Internet', monto='200000.00', dia_vencimiento=12, categoria='internet')
        self._crear_gasto(nombre='Alquiler', monto='300000.00', dia_vencimiento=25, categoria='alquiler')

        with patch('gastos_corrientes.services.gasto_corriente_service.current_user', _FakeAdminUser()):
            with patch('gastos_corrientes.services.gasto_corriente_reporting.date') as mocked_date:
                mocked_date.today.return_value = date(2026, 4, 10)
                mocked_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
                panel = construir_panel_gastos_corrientes(periodo_raw='2026-04')

        self.assertEqual(panel['alertas_activas'], 2)
        alertas_por_nombre = {item['gasto'].nombre: item['alerta'] for item in panel['items']}
        self.assertTrue(alertas_por_nombre['Luz']['activa'])
        self.assertTrue(alertas_por_nombre['Internet']['activa'])
        self.assertFalse(alertas_por_nombre['Alquiler']['activa'])
        self.assertEqual(alertas_por_nombre['Alquiler']['texto'], 'En fecha')

    def test_panel_omite_alerta_inicial_si_el_gasto_nace_despues_del_vencimiento(self):
        self._crear_gasto(
            nombre='Seguro',
            monto='180000.00',
            dia_vencimiento=10,
            categoria='servicios',
            fecha_creacion=datetime(2026, 4, 16, 9, 0, 0),
        )

        with patch('gastos_corrientes.services.gasto_corriente_service.current_user', _FakeAdminUser()):
            with patch('gastos_corrientes.services.gasto_corriente_reporting.date') as mocked_date:
                mocked_date.today.return_value = date(2026, 4, 16)
                mocked_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
                panel_abril = construir_panel_gastos_corrientes(periodo_raw='2026-04')

            with patch('gastos_corrientes.services.gasto_corriente_reporting.date') as mocked_date:
                mocked_date.today.return_value = date(2026, 5, 2)
                mocked_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
                panel_mayo = construir_panel_gastos_corrientes(periodo_raw='2026-05')

        self.assertEqual(len(panel_abril['items']), 0)
        self.assertEqual(PagoGastoCorriente.query.filter_by(periodo_anio=2026, periodo_mes=4).count(), 0)
        self.assertEqual(len(panel_mayo['items']), 1)
        self.assertEqual(panel_mayo['items'][0]['gasto'].nombre, 'Seguro')
        self.assertEqual(PagoGastoCorriente.query.filter_by(periodo_anio=2026, periodo_mes=5).count(), 1)


if __name__ == '__main__':
    unittest.main()
