import unittest
from datetime import datetime

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
        self.servicio_a = servicio_a
        self.servicio_b = servicio_b

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
        self.assertIn('data-dashboard-range=', html)
        self.assertIn('renderCobrosPendientes(data.cobros_pendientes)', html)
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

    def test_resumen_descarta_turno_huerfano_ya_cobrado_en_venta_del_dia(self):
        from app.models import AgendaActividad, DetalleVenta, MetodoPago, PagoVenta, SesionCaja, Venta
        from app.services.dashboard_servicios import obtener_resumen_cobros_pendientes_dashboard

        sesion = SesionCaja(
            id_caja=1,
            id_usuario=self.admin.id_usuario,
            monto_inicial=0,
            estado='abierta',
        )
        actividad = AgendaActividad(
            titulo='Corte premium - Ana Perez',
            tipo='cita',
            fecha_inicio=datetime.utcnow(),
            estado='hecha',
            prioridad='media',
            usuario_id=self.admin.id_usuario,
            creado_por_id=self.admin.id_usuario,
            cliente_id=self.cliente_a.id_cliente,
            origen_modulo='agenda',
            mostrar_agenda_en='solo_responsable',
            recordatorio_a='solo_responsable',
        )
        db.session.add_all([sesion, actividad])
        db.session.flush()

        venta = Venta(
            id_cliente=self.cliente_a.id_cliente,
            id_sesion_caja=sesion.id_sesion,
            id_usuario_vendedor=self.admin.id_usuario,
            subtotal=80000,
            total=80000,
            total_iva_10=7272.73,
            total_iva_5=0,
            total_exenta=0,
            estado='completada',
        )
        db.session.add(venta)
        db.session.flush()
        metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        db.session.add_all([
            DetalleVenta(
                id_venta=venta.id_venta,
                id_servicio=self.servicio_a.id_servicio,
                cantidad=1,
                precio_unitario=80000,
                precio_original=80000,
                porcentaje_iva=10,
                monto_iva=7272.73,
                subtotal=80000,
            ),
            PagoVenta(
                id_venta=venta.id_venta,
                id_metodo_pago=metodo.id_metodo_pago,
                monto=80000,
            ),
        ])
        db.session.commit()

        resumen = obtener_resumen_cobros_pendientes_dashboard(limit=None)
        self.assertEqual(resumen['total_count'], 2)
        self.assertNotIn(
            int(actividad.id),
            {item.get('agenda_actividad_id') for item in resumen['items'] if isinstance(item, dict)},
        )


if __name__ == '__main__':
    unittest.main()
