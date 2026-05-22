import unittest

from app import create_app, db


class TestDashboardServiciosCobrosPendientes(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, Configuracion, Servicio, Usuario
        from app.models.servicio import ClienteServicio

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        Configuracion.establecer('dashboard_negocio_activo', 'servicios')

        self.cliente_a = Cliente(nombre='Ana Perez', tipo='minorista', activo=True)
        self.cliente_b = Cliente(nombre='Bruno Diaz', tipo='minorista', activo=True)
        db.session.add_all([self.cliente_a, self.cliente_b])
        db.session.flush()

        servicio_a = Servicio(
            codigo='DASH-SRV-001',
            nombre='Corte premium',
            categoria='Salon',
            costo=15000,
            precio=80000,
            porcentaje_iva=10,
            activo=True,
        )
        servicio_b = Servicio(
            codigo='DASH-SRV-002',
            nombre='Color completo',
            categoria='Salon',
            costo=30000,
            precio=120000,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add_all([servicio_a, servicio_b])
        db.session.flush()

        self.asignacion_a = ClienteServicio(
            id_cliente=self.cliente_a.id_cliente,
            id_servicio=servicio_a.id_servicio,
            cantidad=1,
            costo_pactado=15000,
            precio_pactado=80000,
            estado='solicitado',
            id_usuario_registro=self.admin.id_usuario,
        )
        self.asignacion_b = ClienteServicio(
            id_cliente=self.cliente_b.id_cliente,
            id_servicio=servicio_b.id_servicio,
            cantidad=1,
            costo_pactado=30000,
            precio_pactado=120000,
            estado='en_proceso',
            id_usuario_registro=self.admin.id_usuario,
        )
        self.asignacion_cancelada = ClienteServicio(
            id_cliente=self.cliente_b.id_cliente,
            id_servicio=servicio_b.id_servicio,
            cantidad=1,
            costo_pactado=30000,
            precio_pactado=90000,
            estado='cancelado',
            id_usuario_registro=self.admin.id_usuario,
        )
        db.session.add_all([self.asignacion_a, self.asignacion_b, self.asignacion_cancelada])
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_dashboard_servicios_muestra_pendientes_reales_y_link_a_pos(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

        html = response.get_data(as_text=True)
        self.assertIn('Cobros pendientes', html)
        self.assertIn('Ana Perez', html)
        self.assertIn('Corte premium', html)
        self.assertIn('Bruno Diaz', html)
        self.assertIn('Color completo', html)
        self.assertIn(f'/ventas/pos?cliente_servicio_id={int(self.asignacion_a.id_cliente_servicio)}', html)
        self.assertIn(f'/ventas/pos?cliente_servicio_id={int(self.asignacion_b.id_cliente_servicio)}', html)
        self.assertIn('Gs. 200.000', html)
        self.assertIn('2 servicios sin cobrar.', html)
        self.assertNotIn('No hay servicios pendientes de cobro ahora mismo.', html)

    def test_api_dashboard_totales_incluye_resumen_cobros_pendientes(self):
        response = self.client.get('/api/dashboard/totales?range=hoy')
        self.assertEqual(response.status_code, 200)

        data = response.get_json() or {}
        cobros = data.get('cobros_pendientes') or {}
        items = cobros.get('items') or []
        self.assertEqual(cobros.get('total_count'), 2)
        self.assertEqual(int(cobros.get('total_monto') or 0), 200000)
        self.assertEqual(len(items), 2)
        self.assertIn('Ana Perez', {item.get('cliente_nombre') for item in items})
        self.assertIn('Bruno Diaz', {item.get('cliente_nombre') for item in items})


if __name__ == '__main__':
    unittest.main()
