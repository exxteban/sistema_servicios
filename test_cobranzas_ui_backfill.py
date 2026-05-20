import unittest
from datetime import timedelta

from app import create_app, db


class TestCobranzasUiBackfill(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, Configuracion, MetodoPago, SesionCaja, Usuario
        from cobranzas import CLAVE_COBRANZAS_ACTIVO, CLAVE_VENTAS_CREDITO_ACTIVO

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.metodo_credito = MetodoPago.query.filter(MetodoPago.nombre.ilike('%Crédito Tienda%')).first()
        self.assertIsNotNone(self.metodo_credito)

        self.metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.assertIsNotNone(self.metodo_efectivo)

        self.cliente = Cliente(
            nombre='Cliente UI Cobranzas',
            ruc_ci='9000002-2',
            tipo='minorista',
            limite_credito=700000,
            activo=True,
        )
        db.session.add(self.cliente)
        db.session.commit()

        self.sesion = SesionCaja(
            id_caja=1,
            id_usuario=self.admin.id_usuario,
            monto_inicial=200000,
            estado='abierta',
        )
        db.session.add(self.sesion)
        db.session.commit()

        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)
        Configuracion.establecer_bool(CLAVE_COBRANZAS_ACTIVO, True)

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

        categoria = Categoria.query.filter_by(nombre='Test UI Cobranzas').first()
        if categoria is None:
            categoria = Categoria(nombre='Test UI Cobranzas', activo=True)
            db.session.add(categoria)
            db.session.flush()

        producto = Producto(
            codigo=codigo,
            nombre=f'Producto {codigo}',
            id_categoria=categoria.id_categoria,
            precio_compra=max(int(precio / 2), 1),
            precio_venta=precio,
            porcentaje_iva=10,
            stock_actual=10,
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
        return data, cuenta

    def test_dashboard_y_listado_muestran_cuentas_credito(self):
        _, cuenta = self._crear_venta_credito('TEST-UI-CRED-001', 120000, 'ui-cobranzas-001')
        cuenta.fecha_vencimiento = cuenta.fecha_vencimiento - timedelta(days=45)
        db.session.commit()

        dashboard = self.client.get('/cobranzas/')
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b'Cobranzas', dashboard.data)
        self.assertIn(b'Cuentas abiertas', dashboard.data)

        listado = self.client.get('/cobranzas/cuentas?estado=vencidas', follow_redirects=True)
        self.assertEqual(listado.status_code, 200)
        self.assertIn(b'Buscar por cliente', listado.data)
        self.assertIn(str(int(cuenta.id_cuenta_cobrar)).encode(), listado.data)
        self.assertIn(b'Ver ficha', listado.data)

        detalle = self.client.get(f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}')
        self.assertEqual(detalle.status_code, 200)
        self.assertIn(b'Historial de cobros', detalle.data)
        self.assertIn(str(int(cuenta.id_venta)).encode(), detalle.data)
        self.assertIn(b'Producto TEST-UI-CRED-001', detalle.data)

        cliente = self.client.get(f'/cobranzas/clientes/{int(self.cliente.id_cliente)}')
        self.assertEqual(cliente.status_code, 200)
        self.assertIn(b'Cobros recientes', cliente.data)
        self.assertIn(str(int(cuenta.id_cuenta_cobrar)).encode(), cliente.data)
        self.assertIn(b'Producto TEST-UI-CRED-001', cliente.data)

    def test_registrar_cobro_html_desde_ficha_actualiza_saldos(self):
        from app.models import Cliente, CuentaPorCobrar

        _, cuenta = self._crear_venta_credito('TEST-UI-COBRO-001', 110000, 'ui-cobro-html-001')

        response = self.client.post(
            f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobrar',
            data={
                'monto': '30000',
                'id_metodo_pago': str(int(self.metodo_efectivo.id_metodo_pago)),
                'referencia': 'REC-HTML-001',
                'observaciones': 'Cobro desde ficha',
                'next_url': f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}',
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Cobro registrado correctamente', response.data)

        cuenta_db = CuentaPorCobrar.query.filter_by(id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar)).first()
        self.assertIsNotNone(cuenta_db)
        self.assertAlmostEqual(float(cuenta_db.monto_cobrado or 0), 30000.0)
        self.assertAlmostEqual(float(cuenta_db.saldo_pendiente or 0), 80000.0)

        cliente_db = db.session.get(Cliente, int(self.cliente.id_cliente))
        self.assertAlmostEqual(float(cliente_db.saldo_pendiente or 0), 80000.0)

    def test_registrar_cobro_html_con_impresion_muestra_pantalla_intermedia(self):
        from app.models import CuentaPorCobrar

        _, cuenta = self._crear_venta_credito('TEST-UI-COBRO-PRINT-001', 95000, 'ui-cobro-print-001')
        detalle = self.client.get(f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}')
        self.assertEqual(detalle.status_code, 200)
        self.assertIn(b'modal-confirmar-cobro', detalle.data)
        self.assertIn(b'Confirmar e imprimir', detalle.data)
        self.assertIn(b'data-no-ajax', detalle.data)
        self.assertIn(b'type="button"', detalle.data)
        self.assertIn(b'form.requestSubmit', detalle.data)

        response = self.client.post(
            f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobrar',
            data={
                'monto': '15000',
                'id_metodo_pago': str(int(self.metodo_efectivo.id_metodo_pago)),
                'referencia': 'REC-HTML-PRINT-001',
                'observaciones': 'Cobro con impresion',
                'next_url': f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}',
                'imprimir_ticket': '1',
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Cobro confirmado', html)
        self.assertIn('/cobranzas/cobros/', html)
        self.assertIn('/ticket', html)
        self.assertIn('window.history.replaceState', html)
        self.assertIn('window.location.replace(destino)', html)

        cuenta_db = CuentaPorCobrar.query.filter_by(id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar)).first()
        self.assertIsNotNone(cuenta_db)
        self.assertAlmostEqual(float(cuenta_db.saldo_pendiente or 0), 80000.0)

    def test_get_a_ruta_post_cobrar_redirige_a_detalle(self):
        _, cuenta = self._crear_venta_credito('TEST-UI-COBRO-GET-001', 70000, 'ui-cobro-get-001')

        response = self.client.get(
            f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobrar',
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}', response.headers.get('Location', ''))

    def test_backfill_credito_es_idempotente(self):
        from app.models import Cliente, CuentaPorCobrar, Venta
        from cobranzas.services import backfill_cuentas_por_cobrar_ventas_credito

        data, cuenta = self._crear_venta_credito('TEST-BACKFILL-CRED-001', 90000, 'backfill-cobranzas-001')
        venta = db.session.get(Venta, int(data['id_venta']))
        self.assertIsNotNone(venta)

        db.session.delete(cuenta)
        db.session.commit()
        self.assertIsNone(CuentaPorCobrar.query.filter_by(id_venta=int(venta.id_venta)).first())

        preview = backfill_cuentas_por_cobrar_ventas_credito(dry_run=True)
        self.assertEqual(preview['detectadas'], 1)
        self.assertEqual(preview['creadas'], 0)
        self.assertEqual(preview['ventas'][0]['id_venta'], int(venta.id_venta))

        aplicado = backfill_cuentas_por_cobrar_ventas_credito(dry_run=False)
        self.assertEqual(aplicado['detectadas'], 1)
        self.assertEqual(aplicado['creadas'], 1)

        cuenta_recreada = CuentaPorCobrar.query.filter_by(id_venta=int(venta.id_venta)).first()
        self.assertIsNotNone(cuenta_recreada)
        self.assertAlmostEqual(float(cuenta_recreada.saldo_pendiente or 0), 90000.0)
        self.assertEqual((cuenta_recreada.estado or '').strip().lower(), 'pendiente')

        cliente_db = db.session.get(Cliente, int(self.cliente.id_cliente))
        self.assertAlmostEqual(float(cliente_db.saldo_pendiente or 0), 90000.0)

        segunda_pasada = backfill_cuentas_por_cobrar_ventas_credito(dry_run=False)
        self.assertEqual(segunda_pasada['detectadas'], 0)
        self.assertEqual(segunda_pasada['creadas'], 0)


if __name__ == '__main__':
    unittest.main()
