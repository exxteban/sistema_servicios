import unittest
from datetime import datetime

from app import create_app, db


class TestCajaAnulaciones(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, Configuracion, MetodoPago, Rol, SesionCaja, Usuario
        from cobranzas import CLAVE_COBRANZAS_ACTIVO, CLAVE_VENTAS_CREDITO_ACTIVO

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)
        self.rol_cajero = Rol.query.filter_by(nombre='Cajero').first()
        self.assertIsNotNone(self.rol_cajero)

        self.cliente = db.session.get(Cliente, 1)
        if self.cliente is None:
            self.cliente = Cliente(nombre='Consumidor Final', tipo='minorista', activo=True)
            db.session.add(self.cliente)
            db.session.commit()

        self.metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.assertIsNotNone(self.metodo_efectivo)
        self.metodo_credito = MetodoPago.query.filter(MetodoPago.nombre.ilike('%Crédito Tienda%')).first()
        self.assertIsNotNone(self.metodo_credito)

        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)
        Configuracion.establecer_bool(CLAVE_COBRANZAS_ACTIVO, True)

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

    def _crear_producto_simple(self, codigo='TEST-ANUL-001', precio=50000):
        from app.models import Categoria, Producto

        categoria = Categoria.query.filter_by(nombre='Test Anulaciones').first()
        if categoria is None:
            categoria = Categoria(nombre='Test Anulaciones', activo=True)
            db.session.add(categoria)
            db.session.flush()

        producto = Producto(
            codigo=codigo,
            nombre=f'Producto {codigo}',
            id_categoria=categoria.id_categoria,
            precio_compra=20000,
            precio_venta=precio,
            porcentaje_iva=10,
            stock_actual=20,
            stock_minimo=1,
            es_servicio=False,
            activo=True,
        )
        db.session.add(producto)
        db.session.commit()
        return producto

    def _crear_venta_efectivo(self, producto, client_request_id):
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{
                    'id_producto': int(producto.id_producto),
                    'cantidad': 1,
                }],
                'pagos': [{
                    'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                    'monto': float(producto.precio_venta),
                }],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': client_request_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        return int(data['id_venta'])

    def _crear_cliente_credito(self, nombre, limite_credito=200000):
        from app.models import Cliente

        cliente = Cliente(
            nombre=nombre,
            ruc_ci=f'{nombre[:6].upper()}-TEST',
            tipo='minorista',
            limite_credito=limite_credito,
            activo=True,
        )
        db.session.add(cliente)
        db.session.commit()
        return cliente

    def _crear_venta_credito(self, producto, cliente, client_request_id):
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{
                    'id_producto': int(producto.id_producto),
                    'cantidad': 1,
                }],
                'pagos': [{
                    'id_metodo_pago': int(self.metodo_credito.id_metodo_pago),
                    'monto': float(producto.precio_venta),
                }],
                'id_cliente': int(cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': client_request_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        return int(data['id_venta'])

    def test_calcular_total_efectivo_mantiene_empate_tras_anular_venta_en_efectivo(self):
        from app.models import MovimientoCaja, Venta

        producto = self._crear_producto_simple(precio=50000)
        venta_id = self._crear_venta_efectivo(producto, 'venta-anulada-efectivo-001')

        venta = db.session.get(Venta, venta_id)
        self.assertIsNotNone(venta)
        self.assertAlmostEqual(float(self.sesion.calcular_total_efectivo() or 0), 550000.0)

        response = self.client.post(f'/ventas/{venta_id}/anular', data={})
        self.assertEqual(response.status_code, 302)

        db.session.refresh(venta)
        self.assertEqual(venta.estado, 'anulada')

        movimientos = (
            MovimientoCaja.query
            .filter_by(id_sesion_caja=self.sesion.id_sesion, referencia_id=venta_id)
            .order_by(MovimientoCaja.id_movimiento_caja.asc())
            .all()
        )
        self.assertEqual(len(movimientos), 2)
        self.assertEqual(movimientos[0].tipo, 'ingreso')
        self.assertEqual(movimientos[1].tipo, 'egreso')
        self.assertEqual((movimientos[1].referencia_tipo or '').strip().lower(), 'anulacion_venta')
        self.assertAlmostEqual(float(self.sesion.calcular_total_efectivo() or 0), 500000.0)

    def test_anular_venta_credito_anula_cuenta_y_bloquea_cobros_posteriores(self):
        from app.models import Cliente, CuentaPorCobrar, Venta

        cliente_credito = self._crear_cliente_credito('Cliente Credito Anulacion')
        producto = self._crear_producto_simple(codigo='TEST-ANUL-CRED-001', precio=70000)
        venta_id = self._crear_venta_credito(producto, cliente_credito, 'venta-anulada-credito-001')

        venta = db.session.get(Venta, venta_id)
        cuenta = CuentaPorCobrar.query.filter_by(id_venta=venta_id).first()
        self.assertIsNotNone(cuenta)
        self.assertEqual((cuenta.estado or '').strip().lower(), 'pendiente')

        response = self.client.post(f'/ventas/{venta_id}/anular', data={})
        self.assertEqual(response.status_code, 302)

        db.session.refresh(venta)
        db.session.refresh(cuenta)
        cliente_db = db.session.get(Cliente, int(cliente_credito.id_cliente))
        self.assertEqual((venta.estado or '').strip().lower(), 'anulada')
        self.assertEqual((cuenta.estado or '').strip().lower(), 'anulada')
        self.assertAlmostEqual(float(venta.saldo_pendiente or 0), 0.0)
        self.assertAlmostEqual(float(cuenta.saldo_pendiente or 0), 0.0)
        self.assertAlmostEqual(float(cliente_db.saldo_pendiente or 0), 0.0)

        cobro = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 10000,
            },
        )
        self.assertEqual(cobro.status_code, 400)
        self.assertIn('anulada', (cobro.get_json() or {}).get('mensaje', '').lower())

    def test_anular_venta_credito_rechaza_si_tiene_cobros_activos(self):
        from app.models import CuentaPorCobrar, Producto, Venta

        cliente_credito = self._crear_cliente_credito('Cliente Credito Con Cobro')
        producto = self._crear_producto_simple(codigo='TEST-ANUL-CRED-002', precio=90000)
        venta_id = self._crear_venta_credito(producto, cliente_credito, 'venta-anulada-credito-002')
        cuenta = CuentaPorCobrar.query.filter_by(id_venta=venta_id).first()
        self.assertIsNotNone(cuenta)

        cobro = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 20000,
            },
        )
        self.assertEqual(cobro.status_code, 200)

        response = self.client.post(f'/ventas/{venta_id}/anular', data={}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        venta = db.session.get(Venta, venta_id)
        producto_db = db.session.get(Producto, int(producto.id_producto))
        db.session.refresh(cuenta)
        self.assertEqual((venta.estado or '').strip().lower(), 'completada')
        self.assertEqual((cuenta.estado or '').strip().lower(), 'pendiente')
        self.assertAlmostEqual(float(cuenta.saldo_pendiente or 0), 70000.0)
        self.assertEqual(int(producto_db.stock_actual or 0), 19)

    def test_informe_y_modal_anulaciones_efectivo_no_duplican_auditoria_repetida(self):
        from app.models import Auditoria, Venta
        from app.routes.caja.common import _calcular_informe_cierre_sesion

        producto = self._crear_producto_simple(codigo='TEST-ANUL-DUP-001', precio=50000)
        venta_id = self._crear_venta_efectivo(producto, 'venta-anulada-dup-001')

        response = self.client.post(f'/ventas/{venta_id}/anular', data={})
        self.assertEqual(response.status_code, 302)

        auditoria_base = (
            Auditoria.query
            .filter_by(
                accion='anular_venta',
                modulo='ventas',
                referencia_tipo='venta',
                referencia_id=venta_id,
            )
            .order_by(Auditoria.id_auditoria.asc())
            .first()
        )
        self.assertIsNotNone(auditoria_base)

        db.session.add(
            Auditoria(
                id_usuario=self.admin.id_usuario,
                accion='anular_venta',
                modulo='ventas',
                descripcion='Duplicado de prueba',
                referencia_tipo='venta',
                referencia_id=venta_id,
                fecha_accion=datetime.utcnow(),
            )
        )
        db.session.commit()

        informe = _calcular_informe_cierre_sesion(self.sesion)
        concepto = next(
            row for row in informe['conceptos']
            if row['concepto'] == 'Anulaciones - Efectivo'
        )
        self.assertAlmostEqual(float(concepto['salida'] or 0), 50000.0)
        self.assertAlmostEqual(float(informe['total_efectivo_sistema'] or 0), 500000.0)

        detalle = self.client.get(
            f'/caja/cierres/{int(self.sesion.id_sesion)}/conceptos/transacciones',
            query_string={
                'key': 'anulaciones_ventas_metodo',
                'metodo_id': int(self.metodo_efectivo.id_metodo_pago),
            },
        )
        self.assertEqual(detalle.status_code, 200)
        data = detalle.get_json() or {}
        self.assertAlmostEqual(float(data.get('salida_total') or 0), 50000.0)
        self.assertEqual(len(data.get('items') or []), 1)

        venta = db.session.get(Venta, venta_id)
        self.assertEqual((venta.estado or '').strip().lower(), 'anulada')

    def test_anular_venta_rechaza_si_la_sesion_ya_fue_cerrada(self):
        from app.models import MovimientoCaja, Venta

        producto = self._crear_producto_simple(codigo='TEST-ANUL-CERRADA-001', precio=60000)
        venta_id = self._crear_venta_efectivo(producto, 'venta-anulada-cerrada-001')

        self.sesion.estado = 'cerrada'
        self.sesion.fecha_cierre = datetime.utcnow()
        db.session.commit()

        response = self.client.post(f'/ventas/{venta_id}/anular', data={}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        venta = db.session.get(Venta, venta_id)
        self.assertEqual((venta.estado or '').strip().lower(), 'completada')

        movimientos = (
            MovimientoCaja.query
            .filter_by(id_sesion_caja=self.sesion.id_sesion, referencia_id=venta_id)
            .order_by(MovimientoCaja.id_movimiento_caja.asc())
            .all()
        )
        self.assertEqual(len(movimientos), 1)
        self.assertEqual((movimientos[0].tipo or '').strip().lower(), 'ingreso')


if __name__ == '__main__':
    unittest.main()
