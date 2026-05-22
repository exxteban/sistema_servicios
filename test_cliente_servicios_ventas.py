import unittest

from app import create_app, db


class TestClienteServiciosVentas(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, MetodoPago, SesionCaja, Usuario

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.cliente = db.session.get(Cliente, 1)
        if self.cliente is None:
            self.cliente = Cliente(nombre='Consumidor Final', tipo='minorista', activo=True)
            db.session.add(self.cliente)
            db.session.commit()

        self.metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.assertIsNotNone(self.metodo_efectivo)

        self.sesion = SesionCaja(
            id_caja=1,
            id_usuario=self.admin.id_usuario,
            monto_inicial=500000,
            estado='abierta',
        )
        db.session.add(self.sesion)
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _crear_servicio_y_asignacion(self, codigo, precio_catalogo=50000, precio_pactado=45000):
        from app.models import ClienteServicio, Servicio

        servicio = Servicio(
            codigo=codigo,
            nombre=f'Servicio {codigo}',
            categoria='QA',
            costo=20000,
            precio=precio_catalogo,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add(servicio)
        db.session.flush()

        asignacion = ClienteServicio(
            id_cliente=self.cliente.id_cliente,
            id_servicio=servicio.id_servicio,
            cantidad=1,
            costo_pactado=20000,
            precio_pactado=precio_pactado,
            estado='solicitado',
            observaciones='Asignacion de prueba',
            id_usuario_registro=self.admin.id_usuario,
        )
        db.session.add(asignacion)
        db.session.commit()
        return servicio, asignacion

    def _cobrar_asignacion(self, asignacion, servicio, client_request_id):
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{
                    'tipo': 'servicio',
                    'id_servicio': int(servicio.id_servicio),
                    'cantidad': 1,
                    'precio': float(asignacion.precio_pactado),
                    'precio_base': float(servicio.precio),
                    'precio_manual': True,
                }],
                'pagos': [{
                    'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                    'monto': float(asignacion.precio_pactado),
                }],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'cliente_servicio_id': int(asignacion.id_cliente_servicio),
                'client_request_id': client_request_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        return int(data['id_venta'])

    def _cobrar_asignaciones(self, asignaciones, servicios, client_request_id):
        items = []
        total = 0.0
        for asignacion, servicio in zip(asignaciones, servicios):
            precio = float(asignacion.precio_pactado)
            items.append({
                'tipo': 'servicio',
                'id_servicio': int(servicio.id_servicio),
                'cantidad': int(asignacion.cantidad),
                'precio': precio,
                'precio_base': float(servicio.precio),
                'precio_manual': True,
            })
            total += precio * float(asignacion.cantidad or 1)

        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': items,
                'pagos': [{
                    'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                    'monto': total,
                }],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'cliente_servicio_ids': [int(asignacion.id_cliente_servicio) for asignacion in asignaciones],
                'client_request_id': client_request_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        return int(data['id_venta'])

    def test_cobrar_cliente_servicio_redirige_a_pos_y_cierra_asignacion(self):
        from app.models import ClienteServicio, Venta

        servicio, asignacion = self._crear_servicio_y_asignacion(
            codigo='TEST-SRV-VENTA-001',
            precio_catalogo=50000,
            precio_pactado=45000,
        )

        cobrar = self.client.get(f'/clientes/{int(self.cliente.id_cliente)}/servicios/{int(asignacion.id_cliente_servicio)}/cobrar')
        self.assertEqual(cobrar.status_code, 302)
        self.assertIn(f'/ventas/pos?cliente_servicio_id={int(asignacion.id_cliente_servicio)}', cobrar.headers.get('Location', ''))

        venta_id = self._cobrar_asignacion(asignacion, servicio, 'cliente-servicio-venta-001')

        venta = db.session.get(Venta, venta_id)
        asignacion_db = db.session.get(ClienteServicio, int(asignacion.id_cliente_servicio))
        self.assertIsNotNone(venta)
        self.assertEqual((venta.estado or '').strip().lower(), 'completada')
        self.assertEqual((asignacion_db.estado or '').strip().lower(), 'completado')
        self.assertEqual(int(asignacion_db.id_venta), int(venta_id))
        self.assertIsNotNone(asignacion_db.fecha_cierre)
        self.assertIn(f'Cobrado en venta #{venta_id}', asignacion_db.observaciones or '')

        detalle = self.client.get(f'/ventas/{venta_id}')
        self.assertEqual(detalle.status_code, 200)
        html = detalle.get_data(as_text=True)
        self.assertIn('Servicios del cliente cobrados en esta venta', html)
        self.assertIn(f'/clientes/{int(self.cliente.id_cliente)}/servicios#cliente-servicio-{int(asignacion.id_cliente_servicio)}', html)

    def test_anular_venta_reabre_cliente_servicio_cobrado(self):
        from app.models import ClienteServicio, Venta

        servicio, asignacion = self._crear_servicio_y_asignacion(
            codigo='TEST-SRV-VENTA-002',
            precio_catalogo=60000,
            precio_pactado=52000,
        )
        venta_id = self._cobrar_asignacion(asignacion, servicio, 'cliente-servicio-venta-002')

        response = self.client.post(f'/ventas/{venta_id}/anular', data={})
        self.assertEqual(response.status_code, 302)

        venta = db.session.get(Venta, venta_id)
        asignacion_db = db.session.get(ClienteServicio, int(asignacion.id_cliente_servicio))
        self.assertEqual((venta.estado or '').strip().lower(), 'anulada')
        self.assertEqual((asignacion_db.estado or '').strip().lower(), 'solicitado')
        self.assertIsNone(asignacion_db.id_venta)
        self.assertIsNone(asignacion_db.fecha_cierre)
        self.assertIn(f'Reabierto por anulaci\u00f3n de venta #{venta_id}', asignacion_db.observaciones or '')

    def test_cobrar_varias_asignaciones_del_cliente_en_una_sola_venta(self):
        from app.models import ClienteServicio, Venta

        servicio_1, asignacion_1 = self._crear_servicio_y_asignacion(
            codigo='TEST-SRV-LOTE-001',
            precio_catalogo=70000,
            precio_pactado=65000,
        )
        servicio_2, asignacion_2 = self._crear_servicio_y_asignacion(
            codigo='TEST-SRV-LOTE-002',
            precio_catalogo=30000,
            precio_pactado=28000,
        )

        cobrar = self.client.post(
            f'/clientes/{int(self.cliente.id_cliente)}/servicios/cobrar-seleccionados',
            data={'cliente_servicio_ids': [int(asignacion_1.id_cliente_servicio), int(asignacion_2.id_cliente_servicio)]},
        )
        self.assertEqual(cobrar.status_code, 302)
        location = cobrar.headers.get('Location', '')
        self.assertIn('/ventas/pos?cliente_servicio_ids=', location)
        self.assertIn(str(int(asignacion_1.id_cliente_servicio)), location)
        self.assertIn(str(int(asignacion_2.id_cliente_servicio)), location)

        venta_id = self._cobrar_asignaciones(
            [asignacion_1, asignacion_2],
            [servicio_1, servicio_2],
            'cliente-servicio-lote-001',
        )

        venta = db.session.get(Venta, venta_id)
        asignacion_1_db = db.session.get(ClienteServicio, int(asignacion_1.id_cliente_servicio))
        asignacion_2_db = db.session.get(ClienteServicio, int(asignacion_2.id_cliente_servicio))
        self.assertEqual((venta.estado or '').strip().lower(), 'completada')
        self.assertEqual((asignacion_1_db.estado or '').strip().lower(), 'completado')
        self.assertEqual((asignacion_2_db.estado or '').strip().lower(), 'completado')
        self.assertEqual(int(asignacion_1_db.id_venta), int(venta_id))
        self.assertEqual(int(asignacion_2_db.id_venta), int(venta_id))

        anular = self.client.post(f'/ventas/{venta_id}/anular', data={})
        self.assertEqual(anular.status_code, 302)

        asignacion_1_reabierta = db.session.get(ClienteServicio, int(asignacion_1.id_cliente_servicio))
        asignacion_2_reabierta = db.session.get(ClienteServicio, int(asignacion_2.id_cliente_servicio))
        self.assertEqual((asignacion_1_reabierta.estado or '').strip().lower(), 'solicitado')
        self.assertEqual((asignacion_2_reabierta.estado or '').strip().lower(), 'solicitado')
        self.assertIsNone(asignacion_1_reabierta.id_venta)
        self.assertIsNone(asignacion_2_reabierta.id_venta)


if __name__ == '__main__':
    unittest.main()
