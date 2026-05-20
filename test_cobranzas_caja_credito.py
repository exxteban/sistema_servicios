import unittest
from datetime import date, timedelta

from app import create_app, db


class TestCobranzasCajaCredito(unittest.TestCase):
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
            nombre='Cliente Cola Crédito',
            ruc_ci='9000010-1',
            tipo='minorista',
            limite_credito=2000000,
            activo=True,
        )
        db.session.add(self.cliente)
        db.session.commit()

        self.sesion = SesionCaja(
            id_caja=1,
            id_usuario=self.admin.id_usuario,
            monto_inicial=400000,
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

    def _crear_producto_simple(self, codigo='TEST-COLA-CRED-001', precio=90000):
        from app.models import Categoria, Producto

        categoria = Categoria.query.filter_by(nombre='Test Cola Crédito').first()
        if categoria is None:
            categoria = Categoria(nombre='Test Cola Crédito', activo=True)
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

    def _crear_venta_credito_cuotas(self, *, codigo='TEST-COLA-CRED-001', precio=90000, request_id='cola-credito-001'):
        from app.models import CuentaPorCobrar

        producto = self._crear_producto_simple(codigo=codigo, precio=precio)
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
                    'tasa_interes_pct': 0,
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        cuenta = CuentaPorCobrar.query.filter_by(id_venta=int(data['id_venta'])).first()
        self.assertIsNotNone(cuenta)
        return cuenta

    def test_enviar_cobro_credito_a_caja_crea_pendiente_con_metadata_completa(self):
        from app.models import ColaCobro

        cuenta = self._crear_venta_credito_cuotas(request_id='cola-credito-enviar-001')

        response = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/enviar-a-caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))

        pendiente = db.session.get(ColaCobro, int(data['cola_id']))
        self.assertIsNotNone(pendiente)
        self.assertEqual((pendiente.tipo_origen or '').strip().lower(), 'cobro_credito')
        self.assertEqual(int(pendiente.id_origen), int(cuenta.id_cuenta_cobrar))
        self.assertAlmostEqual(float(pendiente.monto_total or 0), 30000.0)

        metadata = pendiente.get_metadata()
        self.assertEqual(int(metadata['id_cuenta_cobrar']), int(cuenta.id_cuenta_cobrar))
        self.assertEqual(int(metadata['id_cliente']), int(self.cliente.id_cliente))
        self.assertEqual(metadata['cliente_nombre'], self.cliente.nombre)
        self.assertEqual(int(metadata['id_venta']), int(cuenta.id_venta))
        self.assertAlmostEqual(float(metadata['saldo_pendiente'] or 0), 90000.0)
        self.assertAlmostEqual(float(metadata['monto_sugerido'] or 0), 30000.0)
        self.assertEqual(int(metadata['proxima_cuota']['numero_cuota']), 1)

    def test_cobrar_pendiente_credito_desde_caja_registra_cliente_y_cuotas(self):
        from app.models import ColaCobro, MovimientoCaja, PagoCuentaCobrar

        cuenta = self._crear_venta_credito_cuotas(request_id='cola-credito-cobro-001')
        response_envio = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/enviar-a-caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response_envio.status_code, 200)
        cola_id = int((response_envio.get_json() or {})['cola_id'])

        response_tomar = self.client.post(
            f'/caja/api/cola-cobro/{cola_id}/tomar',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response_tomar.status_code, 200)
        redirect_url = (response_tomar.get_json() or {}).get('redirect_url') or ''
        self.assertIn(f'/cobranzas/cola-cobro/{cola_id}/pos', redirect_url)

        response_cobro = self.client.post(
            f'/caja/api/cola-cobro/{cola_id}/cobrar',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 45000,
                'referencia': 'REC-COLA-001',
            },
        )
        self.assertEqual(response_cobro.status_code, 200)
        data = response_cobro.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertEqual(int(data['numero_cuota_principal']), 1)
        self.assertAlmostEqual(float(data['saldo_pendiente'] or 0), 45000.0)

        pago = db.session.get(PagoCuentaCobrar, int(data['id_pago_cuenta']))
        self.assertIsNotNone(pago)
        self.assertEqual(pago.cliente_nombre_snapshot, self.cliente.nombre)
        self.assertEqual(int(pago.numero_cuota_principal or 0), 1)
        self.assertIsNotNone(pago.id_cuota_credito_principal)

        detalle = pago.get_detalle_aplicacion()
        self.assertEqual(detalle['cliente_nombre'], self.cliente.nombre)
        self.assertEqual([int(item['numero_cuota']) for item in detalle['cuotas_aplicadas']], [1, 2])
        self.assertAlmostEqual(float(detalle['saldo_cuenta_antes'] or 0), 90000.0)
        self.assertAlmostEqual(float(detalle['saldo_cuenta_despues'] or 0), 45000.0)

        movimiento = db.session.get(MovimientoCaja, int(data['movimiento_caja_id']))
        self.assertIsNotNone(movimiento)
        self.assertIn(self.cliente.nombre, movimiento.motivo)
        self.assertIn('Cuota #1', movimiento.motivo)

        pendiente = db.session.get(ColaCobro, cola_id)
        self.assertEqual((pendiente.estado or '').strip().lower(), 'cobrado')
        metadata = pendiente.get_metadata()
        self.assertEqual(int(metadata['id_pago_cuenta']), int(pago.id_pago_cuenta))
        self.assertEqual(int(metadata['numero_cuota_principal']), 1)
        self.assertEqual(metadata['cliente_nombre'], self.cliente.nombre)

    def test_ticket_cobro_muestra_comprobante_y_desglose_de_cuotas(self):
        cuenta = self._crear_venta_credito_cuotas(request_id='cola-credito-ticket-001')
        response_cobro = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 45000,
                'referencia': 'REC-TICKET-001',
            },
        )
        self.assertEqual(response_cobro.status_code, 200)
        pago_id = int((response_cobro.get_json() or {})['id_pago_cuenta'])

        response_ticket = self.client.get(f'/cobranzas/cobros/{pago_id}/ticket?preview=1')

        self.assertEqual(response_ticket.status_code, 200)
        html = response_ticket.get_data(as_text=True)
        self.assertIn('COMPROBANTE DE PAGO', html)
        self.assertIn(f'COB-{pago_id:06d}', html)
        self.assertIn('Comprobante venta:', html)
        self.assertIn('Cuota principal:', html)
        self.assertIn('de 3', html)
        self.assertIn('Aplicado a cuotas', html)
        self.assertIn('Cuota #1', html)
        self.assertIn('Cuota #2', html)
        self.assertIn('REC-TICKET-001', html)

    def test_pos_html_toma_pendiente_antes_de_mostrar_formulario(self):
        from app.models import ColaCobro

        cuenta = self._crear_venta_credito_cuotas(request_id='cola-credito-html-tomar-001')
        response_envio = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/enviar-a-caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response_envio.status_code, 200)
        cola_id = int((response_envio.get_json() or {})['cola_id'])

        response = self.client.get(f'/cobranzas/cola-cobro/{cola_id}/pos')

        self.assertEqual(response.status_code, 200)
        pendiente = db.session.get(ColaCobro, cola_id)
        self.assertEqual((pendiente.estado or '').strip().lower(), 'en_proceso')
        self.assertEqual(int(pendiente.id_usuario_destino or 0), int(self.admin.id_usuario))
        self.assertIsNotNone(pendiente.fecha_toma)

    def test_servicio_no_cobra_pendiente_sin_tomar(self):
        from app.models import ColaCobro
        from cobranzas.services import registrar_cobro_credito_desde_cola

        cuenta = self._crear_venta_credito_cuotas(request_id='cola-credito-servicio-sin-tomar-001')
        response_envio = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/enviar-a-caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response_envio.status_code, 200)
        cola_id = int((response_envio.get_json() or {})['cola_id'])

        pendiente = db.session.get(ColaCobro, cola_id)
        with self.assertRaisesRegex(ValueError, 'Debe tomar el pendiente antes de cobrarlo'):
            registrar_cobro_credito_desde_cola(
                pendiente,
                id_usuario=int(self.admin.id_usuario),
                id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
                monto=30000,
                sesion=self.sesion,
            )

    def test_post_html_no_cobra_pendiente_cancelado(self):
        from app.models import ColaCobro, PagoCuentaCobrar

        cuenta = self._crear_venta_credito_cuotas(request_id='cola-credito-html-cancelado-001')
        response_envio = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/enviar-a-caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response_envio.status_code, 200)
        cola_id = int((response_envio.get_json() or {})['cola_id'])

        pendiente = db.session.get(ColaCobro, cola_id)
        pendiente.estado = 'cancelado'
        db.session.commit()

        response = self.client.post(
            f'/cobranzas/cola-cobro/{cola_id}/cobrar',
            data={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 30000,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/caja/', response.headers.get('Location') or '')
        self.assertEqual(PagoCuentaCobrar.query.filter_by(id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar)).count(), 0)
        self.assertEqual((db.session.get(ColaCobro, cola_id).estado or '').strip().lower(), 'cancelado')

    def test_estado_caja_y_resumen_exponen_cobros_credito_en_cola(self):
        from app.models import Configuracion

        Configuracion.establecer_bool('caja_alerta_pendientes_activa', True)
        cuenta = self._crear_venta_credito_cuotas(request_id='cola-credito-ui-001')
        response_envio = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/enviar-a-caja',
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response_envio.status_code, 200)

        response_estado = self.client.get('/caja/')
        self.assertEqual(response_estado.status_code, 200)
        html = response_estado.get_data(as_text=True)
        self.assertIn('value="cobro_credito"', html)
        self.assertIn('data-cola-tipo="cobro_credito"', html)
        self.assertIn('Abrir cobro', html)

        response_resumen = self.client.get('/caja/api/cola-cobro/resumen')
        self.assertEqual(response_resumen.status_code, 200)
        data = response_resumen.get_json() or {}
        self.assertEqual(int(((data.get('totales') or {}).get('cobro_credito') or 0)), 1)
        pendientes = data.get('pendientes') or []
        self.assertTrue(pendientes)
        self.assertEqual((pendientes[0].get('tipo_origen') or '').strip().lower(), 'cobro_credito')
