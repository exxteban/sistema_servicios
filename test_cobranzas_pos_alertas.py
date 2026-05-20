import unittest

from app import create_app, db


class TestCobranzasPosAlertas(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, Configuracion, MetodoPago, SesionCaja, Usuario
        from cobranzas import CLAVE_COBRANZAS_ACTIVO, CLAVE_VENTAS_CREDITO_ACTIVO

        self.clave_cobranzas = CLAVE_COBRANZAS_ACTIVO
        self.clave_credito = CLAVE_VENTAS_CREDITO_ACTIVO

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.metodo_credito = MetodoPago.query.filter(MetodoPago.nombre.ilike('%Tienda%')).first()
        self.assertIsNotNone(self.metodo_credito)

        self.cliente = Cliente(
            nombre='Cliente POS Credito',
            ruc_ci='9000003-3',
            tipo='minorista',
            limite_credito=900000,
            activo=True,
        )
        db.session.add(self.cliente)
        db.session.commit()

        self.sesion = SesionCaja(
            id_caja=1,
            id_usuario=self.admin.id_usuario,
            monto_inicial=150000,
            estado='abierta',
        )
        db.session.add(self.sesion)
        db.session.commit()

        Configuracion.establecer_bool(self.clave_credito, False)
        Configuracion.establecer_bool(self.clave_cobranzas, False)

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _crear_producto_simple(self, codigo, precio):
        from app.models import Categoria, Producto

        categoria = Categoria.query.filter_by(nombre='Test POS Alertas').first()
        if categoria is None:
            categoria = Categoria(nombre='Test POS Alertas', activo=True)
            db.session.add(categoria)
            db.session.flush()

        producto = Producto(
            codigo=codigo,
            nombre=f'Producto {codigo}',
            id_categoria=categoria.id_categoria,
            precio_compra=max(int(precio / 2), 1),
            precio_venta=precio,
            porcentaje_iva=10,
            stock_actual=12,
            stock_minimo=1,
            es_servicio=False,
            activo=True,
        )
        db.session.add(producto)
        db.session.commit()
        return producto

    def _crear_venta_credito(self, codigo, precio, request_id):
        from app.models import CuentaPorCobrar

        producto = self._crear_producto_simple(codigo, precio)
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': precio}],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': request_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        cuenta = CuentaPorCobrar.query.filter_by(id_venta=int(data['id_venta'])).first()
        self.assertIsNotNone(cuenta)
        return cuenta

    def test_api_resumen_cliente_devuelve_deuda_para_pos_sin_cobranzas(self):
        from app.models import Configuracion

        Configuracion.establecer_bool(self.clave_credito, True)
        cuenta = self._crear_venta_credito('TEST-POS-ALERTA-001', 85000, 'pos-alerta-credito-001')

        response = self.client.get(f'/cobranzas/api/clientes/{int(self.cliente.id_cliente)}/resumen')

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertEqual(int(data.get('cliente_id') or 0), int(self.cliente.id_cliente))
        self.assertAlmostEqual(float(data.get('saldo_total') or 0), 85000.0)
        self.assertEqual(int(data.get('cuentas_abiertas') or 0), 1)
        self.assertEqual(int(data.get('cuentas_vencidas') or 0), 0)
        self.assertAlmostEqual(float(data.get('limite_credito') or 0), 900000.0)
        self.assertAlmostEqual(float(data.get('credito_disponible') or 0), 815000.0)
        self.assertTrue(bool(data.get('tiene_deuda')))
        self.assertEqual(int(data.get('cuenta_prioritaria_id') or 0), int(cuenta.id_cuenta_cobrar))
        self.assertIsNone(data.get('url_cliente'))
        self.assertIsNone(data.get('url_cobrar'))

    def test_api_resumen_cliente_expone_urls_si_cobranzas_esta_activo(self):
        from app.models import Configuracion

        Configuracion.establecer_bool(self.clave_credito, True)
        Configuracion.establecer_bool(self.clave_cobranzas, True)
        cuenta = self._crear_venta_credito('TEST-POS-ALERTA-002', 92000, 'pos-alerta-credito-002')

        response = self.client.get(f'/cobranzas/api/clientes/{int(self.cliente.id_cliente)}/resumen')

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertIn(f'/cobranzas/clientes/{int(self.cliente.id_cliente)}', data.get('url_cliente') or '')
        self.assertIn(f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}', data.get('url_cobrar') or '')


if __name__ == '__main__':
    unittest.main()
