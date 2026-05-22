import unittest

from app import create_app, db


class TestCajaCobrosPendientesPage(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Caja, Cliente, ColaCobro, Configuracion, Servicio, SesionCaja, Usuario
        from app.models.servicio import ClienteServicio

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.caja = Caja(nombre='Caja Cobros Pendientes QA', ubicacion='Mostrador', activa=True)
        db.session.add(self.caja)
        db.session.flush()

        self.sesion = SesionCaja(
            id_caja=self.caja.id_caja,
            id_usuario=self.admin.id_usuario,
            monto_inicial=0,
            estado='abierta',
        )
        self.cliente = Cliente(nombre='Cliente Cola QA', tipo='minorista', activo=True)
        self.cliente_servicio = Cliente(nombre='Cliente Servicio QA', tipo='minorista', activo=True)
        self.servicio = Servicio(
            codigo='SERV-QA-COBRO',
            nombre='Servicio Pendiente QA',
            categoria='Salon',
            costo=10000,
            precio=45000,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add_all([self.sesion, self.cliente, self.cliente_servicio, self.servicio])
        db.session.flush()

        self.pendiente = ColaCobro(
            tipo_origen='venta',
            id_origen=321,
            id_cliente=self.cliente.id_cliente,
            monto_total=125000,
            id_usuario_origen=self.admin.id_usuario,
            estado='pendiente',
        )
        self.pendiente.set_metadata({'items': [{'cantidad': 1, 'nombre': 'Servicio QA'}]})
        self.asignacion_pendiente = ClienteServicio(
            id_cliente=self.cliente_servicio.id_cliente,
            id_servicio=self.servicio.id_servicio,
            cantidad=1,
            costo_pactado=10000,
            precio_pactado=45000,
            estado='solicitado',
            id_usuario_registro=self.admin.id_usuario,
        )
        db.session.add_all([self.pendiente, self.asignacion_pendiente])
        db.session.commit()

        Configuracion.establecer_bool('caja_alerta_pendientes_activa', False)

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_pagina_dedicada_muestra_pendientes_reales_y_cola_aunque_alerta_global_este_desactivada(self):
        response = self.client.get('/caja/cobros-pendientes')
        self.assertEqual(response.status_code, 200)

        html = response.get_data(as_text=True)
        self.assertIn('Cobros pendientes', html)
        self.assertIn('Pendientes reales de cobro', html)
        self.assertIn('Cliente Servicio QA', html)
        self.assertIn('Servicio Pendiente QA', html)
        self.assertIn(f'/ventas/pos?cliente_servicio_id={int(self.asignacion_pendiente.id_cliente_servicio)}', html)
        self.assertIn('Cola de cobros', html)
        self.assertIn('Cliente Cola QA', html)
        self.assertIn('Venta enviada', html)

    def test_api_resumen_permte_forzar_actualizacion_en_pagina_dedicada(self):
        response = self.client.get('/caja/api/cola-cobro/resumen?detalle=1&firma=1&forzar_activa=1&cola_estado=pendiente')
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertTrue(data['alerta_activa'])
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['filtros']['cola_estado'], 'pendiente')


if __name__ == '__main__':
    unittest.main()
