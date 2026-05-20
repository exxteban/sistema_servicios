import unittest
from datetime import date, datetime, timedelta

from app import create_app, db


class TestCobranzasCuotas(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, Configuracion, MetodoPago, SesionCaja, Usuario
        from cobranzas import CLAVE_COBRANZAS_ACTIVO, CLAVE_VENTAS_CREDITO_ACTIVO

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.assertIsNotNone(self.metodo_efectivo)

        self.metodo_credito = MetodoPago.query.filter(MetodoPago.nombre.ilike('%tienda%')).first()
        self.assertIsNotNone(self.metodo_credito)

        self.cliente = Cliente(
            nombre='Cliente Cuotas Test',
            ruc_ci='9000005-5',
            tipo='minorista',
            limite_credito=1500000,
            activo=True,
        )
        db.session.add(self.cliente)
        db.session.commit()

        self.sesion = SesionCaja(
            id_caja=1,
            id_usuario=self.admin.id_usuario,
            monto_inicial=500000,
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

        categoria = Categoria.query.filter_by(nombre='Test Cuotas').first()
        if categoria is None:
            categoria = Categoria(nombre='Test Cuotas', activo=True)
            db.session.add(categoria)
            db.session.flush()

        producto = Producto(
            codigo=codigo,
            nombre=f'Producto {codigo}',
            id_categoria=categoria.id_categoria,
            precio_compra=max(int(precio / 2), 1),
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

    def _crear_venta_credito_cuotas(
        self,
        codigo='TEST-CUOTAS-001',
        precio=90000,
        request_id='venta-cuotas-001',
        tasa_interes_pct=0,
    ):
        from app.models import CuentaPorCobrar, PlanCreditoVenta

        producto = self._crear_producto_simple(codigo, precio)
        primer_vencimiento = (date.today() + timedelta(days=30)).isoformat()
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': precio}],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': request_id,
                'credito_modo': 'cuotas',
                'credito_plan': {
                    'cantidad_cuotas': 3,
                    'frecuencia_dias': 30,
                    'fecha_primer_vencimiento': primer_vencimiento,
                    'tasa_interes_pct': tasa_interes_pct,
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        cuenta = CuentaPorCobrar.query.filter_by(id_venta=int(data['id_venta'])).first()
        self.assertIsNotNone(cuenta)
        plan = PlanCreditoVenta.query.filter_by(id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar)).first()
        self.assertIsNotNone(plan)
        return data, cuenta, plan

    def test_venta_credito_cuotas_crea_plan_y_calendario(self):
        from app.models import CuotaCreditoVenta, Venta

        data, cuenta, plan = self._crear_venta_credito_cuotas()

        self.assertEqual(data.get('credito_modo'), 'cuotas')
        self.assertEqual(int(data.get('id_plan_credito_venta') or 0), int(plan.id_plan_credito_venta))
        self.assertAlmostEqual(float(data.get('credito_tasa_interes_pct') or 0), 0.0)
        self.assertEqual((cuenta.estado or '').strip().lower(), 'pendiente')
        self.assertAlmostEqual(float(cuenta.saldo_pendiente or 0), 90000.0)

        cuotas = (
            CuotaCreditoVenta.query
            .filter_by(id_plan_credito_venta=int(plan.id_plan_credito_venta))
            .order_by(CuotaCreditoVenta.numero_cuota.asc())
            .all()
        )
        self.assertEqual(len(cuotas), 3)
        self.assertEqual([int(c.numero_cuota) for c in cuotas], [1, 2, 3])
        self.assertEqual([float(c.monto_programado or 0) for c in cuotas], [30000.0, 30000.0, 30000.0])
        self.assertEqual(cuotas[0].fecha_vencimiento, date.today() + timedelta(days=30))
        self.assertEqual(cuotas[1].fecha_vencimiento, date.today() + timedelta(days=60))

        venta = db.session.get(Venta, int(cuenta.id_venta))
        self.assertEqual((venta.tipo_venta or '').strip().lower(), 'credito')
        self.assertAlmostEqual(float(venta.saldo_pendiente or 0), 90000.0)

    def test_venta_credito_cuotas_con_interes_genera_totales_financieros(self):
        from app.models import CuotaCreditoVenta

        data, cuenta, plan = self._crear_venta_credito_cuotas(
            codigo='TEST-CUOTAS-INTERES-001',
            precio=100000,
            request_id='venta-cuotas-interes-001',
            tasa_interes_pct=10,
        )

        self.assertEqual(data.get('credito_modo'), 'cuotas')
        self.assertAlmostEqual(float(data.get('credito_tasa_interes_pct') or 0), 10.0)
        self.assertAlmostEqual(float(plan.tasa_periodica_pct or 0), 10.0)
        self.assertAlmostEqual(float(plan.monto_total_financiado or 0), 100000.0)
        self.assertAlmostEqual(float(plan.monto_total_interes or 0), 20634.44, places=2)
        self.assertAlmostEqual(float(plan.monto_total_con_interes or 0), 120634.44, places=2)
        self.assertAlmostEqual(float(cuenta.saldo_pendiente or 0), 120634.44, places=2)

        cuotas = (
            CuotaCreditoVenta.query
            .filter_by(id_plan_credito_venta=int(plan.id_plan_credito_venta))
            .order_by(CuotaCreditoVenta.numero_cuota.asc())
            .all()
        )
        self.assertEqual(len(cuotas), 3)
        self.assertAlmostEqual(float(cuotas[0].interes_programado or 0), 10000.0, places=2)
        self.assertAlmostEqual(float(cuotas[0].capital_programado or 0), 30211.48, places=2)

    def test_venta_credito_cuotas_rechaza_si_interes_supera_limite(self):
        self.cliente.limite_credito = 110000
        db.session.commit()

        producto = self._crear_producto_simple('TEST-CUOTAS-LIMITE-001', 100000)
        primer_vencimiento = (date.today() + timedelta(days=30)).isoformat()
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 100000}],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-cuotas-limite-001',
                'credito_modo': 'cuotas',
                'credito_plan': {
                    'cantidad_cuotas': 3,
                    'frecuencia_dias': 30,
                    'fecha_primer_vencimiento': primer_vencimiento,
                    'tasa_interes_pct': 10,
                },
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        self.assertIn('Credito insuficiente', data.get('error', ''))

        from app.models import CuentaPorCobrar, Venta

        self.assertEqual(CuentaPorCobrar.query.count(), 0)
        self.assertEqual(Venta.query.count(), 0)

    def test_cobro_en_cuotas_imputa_a_cuotas_mas_antiguas(self):
        from app.models import CuotaCreditoVenta, PagoCuentaCobrarAplicacion

        _, cuenta, plan = self._crear_venta_credito_cuotas(codigo='TEST-CUOTAS-COBRO-001', request_id='venta-cuotas-cobro-001')

        response = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 45000,
                'referencia': 'CUOTA-001',
            },
        )
        self.assertEqual(response.status_code, 200)

        cuotas = (
            CuotaCreditoVenta.query
            .filter_by(id_plan_credito_venta=int(plan.id_plan_credito_venta))
            .order_by(CuotaCreditoVenta.numero_cuota.asc())
            .all()
        )
        self.assertEqual((cuotas[0].estado or '').strip().lower(), 'pagada')
        self.assertAlmostEqual(float(cuotas[0].saldo_pendiente or 0), 0.0)
        self.assertAlmostEqual(float(cuotas[1].saldo_pendiente or 0), 15000.0)
        self.assertAlmostEqual(float(cuotas[2].saldo_pendiente or 0), 30000.0)

        aplicaciones = (
            PagoCuentaCobrarAplicacion.query
            .join(PagoCuentaCobrarAplicacion.cuota)
            .filter(CuotaCreditoVenta.id_plan_credito_venta == int(plan.id_plan_credito_venta))
            .order_by(PagoCuentaCobrarAplicacion.id_aplicacion.asc())
            .all()
        )
        self.assertEqual(len(aplicaciones), 2)
        self.assertEqual([float(app.monto_aplicado or 0) for app in aplicaciones], [30000.0, 15000.0])
        self.assertAlmostEqual(float(cuenta.saldo_pendiente or 0), 45000.0)

    def test_cobro_parcial_con_interes_actualiza_saldo_capital_real(self):
        from app.models import CuotaCreditoVenta

        _, cuenta, plan = self._crear_venta_credito_cuotas(
            codigo='TEST-CUOTAS-CAPITAL-REAL-001',
            precio=100000,
            request_id='venta-cuotas-capital-real-001',
            tasa_interes_pct=10,
        )

        response = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 45000,
                'referencia': 'CAPITAL-REAL-001',
            },
        )
        self.assertEqual(response.status_code, 200)

        cuotas = (
            CuotaCreditoVenta.query
            .filter_by(id_plan_credito_venta=int(plan.id_plan_credito_venta))
            .order_by(CuotaCreditoVenta.numero_cuota.asc())
            .all()
        )
        self.assertEqual(len(cuotas), 3)
        self.assertAlmostEqual(float(cuotas[0].saldo_capital or 0), 69788.52, places=2)
        self.assertAlmostEqual(float(cuotas[1].saldo_capital or 0), 69788.52, places=2)
        self.assertAlmostEqual(float(cuotas[2].saldo_capital or 0), 69788.52, places=2)
        self.assertAlmostEqual(float(cuotas[1].saldo_pendiente or 0), 35422.96, places=2)

    def test_anular_cobro_en_cuotas_revierte_aplicaciones(self):
        from app.models import CuotaCreditoVenta, PagoCuentaCobrar

        _, cuenta, plan = self._crear_venta_credito_cuotas(codigo='TEST-CUOTAS-ANULAR-001', request_id='venta-cuotas-anular-001')
        cobro = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 45000,
            },
        )
        self.assertEqual(cobro.status_code, 200)
        cobro_data = cobro.get_json() or {}

        anular = self.client.post(
            f'/cobranzas/api/cobros/{int(cobro_data["id_pago_cuenta"])}/anular',
            json={'motivo_anulacion': 'Prueba de reversa'},
        )
        self.assertEqual(anular.status_code, 200)

        pago = db.session.get(PagoCuentaCobrar, int(cobro_data['id_pago_cuenta']))
        self.assertEqual((pago.estado or '').strip().lower(), 'anulado')

        cuotas = (
            CuotaCreditoVenta.query
            .filter_by(id_plan_credito_venta=int(plan.id_plan_credito_venta))
            .order_by(CuotaCreditoVenta.numero_cuota.asc())
            .all()
        )
        self.assertEqual([float(c.saldo_pendiente or 0) for c in cuotas], [30000.0, 30000.0, 30000.0])
        self.assertEqual((cuotas[0].estado or '').strip().lower(), 'pendiente')
        self.assertAlmostEqual(float(cuenta.saldo_pendiente or 0), 90000.0)

    def test_ficha_cuenta_muestra_plan_y_cuotas(self):
        _, cuenta, _plan = self._crear_venta_credito_cuotas(codigo='TEST-CUOTAS-FICHA-001', request_id='venta-cuotas-ficha-001')

        response = self.client.get(f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Plan en cuotas', html)
        self.assertIn('Próxima cuota', html)
        self.assertIn('#1', html)
        self.assertIn('Cuotas', html)
        self.assertIn('Pendientes', html)
        self.assertIn('value="30000.0"', html)
        self.assertIn('Sugerido desde la proxima cuota #1', html)
        self.assertIn('Producto TEST-CUOTAS-FICHA-001', html)

    def test_ficha_cliente_resume_plan_de_cuotas(self):
        self._crear_venta_credito_cuotas(codigo='TEST-CUOTAS-CLIENTE-001', request_id='venta-cuotas-cliente-001')

        response = self.client.get(f'/cobranzas/clientes/{int(self.cliente.id_cliente)}')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Plan', html)
        self.assertIn('3 cuota(s)', html)
        self.assertIn('Próxima: #1', html)
        self.assertIn('Producto TEST-CUOTAS-CLIENTE-001', html)


    def test_detalle_cuenta_refresca_estado_vencido_de_cuota(self):
        from app.models import CuotaCreditoVenta
        from cobranzas.services import obtener_detalle_cuenta

        _, cuenta, plan = self._crear_venta_credito_cuotas(
            codigo='TEST-CUOTAS-VENCIDA-001',
            request_id='venta-cuotas-vencida-001',
        )
        cuota = (
            CuotaCreditoVenta.query
            .filter_by(id_plan_credito_venta=int(plan.id_plan_credito_venta), numero_cuota=1)
            .first()
        )
        self.assertIsNotNone(cuota)
        cuota.fecha_vencimiento = date.today() - timedelta(days=5)
        cuota.estado = 'pendiente'
        cuota.dias_vencido = 0
        db.session.commit()

        detalle = obtener_detalle_cuenta(int(cuenta.id_cuenta_cobrar))

        self.assertIsNotNone(detalle)
        self.assertEqual(detalle['cuotas'][0]['estado'], 'vencida')
        self.assertEqual(int(detalle['cuotas'][0]['dias_vencido']), 5)
        self.assertEqual(detalle['plan_credito']['cuotas_vencidas'], 1)

    def test_venta_cuotas_acepta_primer_vencimiento_en_hoy_local(self):
        from app.routes.ventas import parte3

        producto = self._crear_producto_simple('TEST-CUOTAS-HOY-LOCAL-001', 120000)
        fecha_local = datetime.utcnow().date() - timedelta(days=1)
        fecha_original = parte3.today_local
        parte3.today_local = lambda: fecha_local

        try:
            response = self.client.post(
                '/ventas/procesar',
                json={
                    'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                    'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 120000}],
                    'id_cliente': int(self.cliente.id_cliente),
                    'id_usuario_vendedor': int(self.admin.id_usuario),
                    'client_request_id': 'venta-cuotas-hoy-local-001',
                    'credito_modo': 'cuotas',
                    'credito_plan': {
                        'cantidad_cuotas': 3,
                        'frecuencia_dias': 30,
                        'fecha_primer_vencimiento': fecha_local.isoformat(),
                    },
                },
            )
        finally:
            parte3.today_local = fecha_original

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('credito_modo'), 'cuotas')


if __name__ == '__main__':
    unittest.main()
