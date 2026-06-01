import unittest

from app import create_app, db


class TestVentasContadoRegresion(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, MetodoPago, Permiso, SesionCaja, Usuario

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.cliente = db.session.get(Cliente, 1)
        self.assertIsNotNone(self.cliente)

        self.metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.assertIsNotNone(self.metodo_efectivo)

        self.metodo_no_efectivo = (
            MetodoPago.query
            .filter(MetodoPago.activo.is_(True), MetodoPago.id_metodo_pago != self.metodo_efectivo.id_metodo_pago)
            .order_by(MetodoPago.orden_display.asc(), MetodoPago.id_metodo_pago.asc())
            .first()
        )
        self.assertIsNotNone(self.metodo_no_efectivo)

        self.metodo_credito = MetodoPago.query.filter(MetodoPago.nombre.ilike('%Crédito Tienda%')).first()
        self.assertIsNotNone(self.metodo_credito)

        self.permiso_credito = Permiso.query.filter_by(codigo='venta_credito').first()
        self.assertIsNotNone(self.permiso_credito)

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

    def _crear_producto_simple(self, codigo, precio):
        from app.models import Categoria, Producto

        categoria = Categoria.query.filter_by(nombre='Test Ventas Contado').first()
        if categoria is None:
            categoria = Categoria(nombre='Test Ventas Contado', activo=True)
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

    def _procesar_venta(self, producto, pagos, client_request_id):
        return self.client.post(
            '/ventas/procesar',
            json={
                'items': [{
                    'id_producto': int(producto.id_producto),
                    'cantidad': 1,
                }],
                'pagos': pagos,
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': client_request_id,
            },
        )

    def test_bootstrap_deja_credito_activo_pero_sigue_bloqueado_sin_flag(self):
        self.assertTrue(bool(self.permiso_credito.activo))
        self.assertTrue(bool(self.permiso_credito.requiere_autorizacion))
        self.assertTrue(bool(self.metodo_credito.activo))

        producto = self._crear_producto_simple('TEST-CRED-BLOCK-001', 90000)
        resp = self._procesar_venta(
            producto,
            [{
                'id_metodo_pago': int(self.metodo_credito.id_metodo_pago),
                'monto': 90000,
            }],
            'venta-credito-sin-flag-001',
        )

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json() or {}
        self.assertIn('cr', (data.get('error') or '').lower())

    def test_venta_credito_total_crea_cuenta_por_cobrar_y_no_genera_pago_venta(self):
        from app.models import Cliente, Configuracion, CuentaPorCobrar, MovimientoCaja, PagoVenta, Venta
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

        producto = self._crear_producto_simple('TEST-CREDITO-TOTAL-001', 90000)
        cliente_credito = Cliente(
            nombre='Cliente Credito Total',
            ruc_ci='8000001-1',
            tipo='minorista',
            limite_credito=300000,
            activo=True,
        )
        db.session.add(cliente_credito)
        db.session.commit()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 90000}],
                'id_cliente': int(cliente_credito.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-credito-total-001',
            },
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get('tipo_venta'), 'credito')
        self.assertAlmostEqual(float(data.get('pagado') or 0), 0.0)
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 90000.0)

        venta = db.session.get(Venta, int(data['id_venta']))
        self.assertEqual((venta.tipo_venta or '').strip().lower(), 'credito')
        self.assertAlmostEqual(float(venta.saldo_pendiente or 0), 90000.0)

        cuenta = CuentaPorCobrar.query.filter_by(id_venta=venta.id_venta).first()
        self.assertIsNotNone(cuenta)
        self.assertAlmostEqual(float(cuenta.monto_total or 0), 90000.0)
        self.assertAlmostEqual(float(cuenta.monto_cobrado or 0), 0.0)
        self.assertAlmostEqual(float(cuenta.saldo_pendiente or 0), 90000.0)
        self.assertEqual((cuenta.estado or '').strip().lower(), 'pendiente')

        cliente_db = db.session.get(Cliente, cliente_credito.id_cliente)
        self.assertAlmostEqual(float(cliente_db.saldo_pendiente or 0), 90000.0)
        self.assertEqual(PagoVenta.query.filter_by(id_venta=venta.id_venta).count(), 0)
        self.assertEqual(MovimientoCaja.query.filter_by(referencia_tipo='venta', referencia_id=venta.id_venta).count(), 0)

    def test_venta_credito_con_anticipo_efectivo_financia_solo_saldo_restante(self):
        from app.models import Cliente, Configuracion, CuentaPorCobrar, MovimientoCaja, PagoVenta, Venta
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

        producto = self._crear_producto_simple('TEST-CREDITO-MIXTO-001', 100000)
        cliente_credito = Cliente(
            nombre='Cliente Credito Mixto',
            ruc_ci='8000002-2',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(cliente_credito)
        db.session.commit()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [
                    {'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 20000},
                    {'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 80000},
                ],
                'id_cliente': int(cliente_credito.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-credito-mixto-001',
            },
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get('tipo_venta'), 'credito')
        self.assertAlmostEqual(float(data.get('pagado') or 0), 20000.0)
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 80000.0)

        venta = db.session.get(Venta, int(data['id_venta']))
        self.assertEqual((venta.tipo_venta or '').strip().lower(), 'credito')
        self.assertAlmostEqual(float(venta.saldo_pendiente or 0), 80000.0)

        pagos = PagoVenta.query.filter_by(id_venta=venta.id_venta).all()
        self.assertEqual(len(pagos), 1)
        self.assertEqual(int(pagos[0].id_metodo_pago), int(self.metodo_efectivo.id_metodo_pago))
        self.assertAlmostEqual(float(pagos[0].monto or 0), 20000.0)

        cuenta = CuentaPorCobrar.query.filter_by(id_venta=venta.id_venta).first()
        self.assertIsNotNone(cuenta)
        self.assertAlmostEqual(float(cuenta.saldo_pendiente or 0), 80000.0)

        cliente_db = db.session.get(Cliente, cliente_credito.id_cliente)
        self.assertAlmostEqual(float(cliente_db.saldo_pendiente or 0), 80000.0)

        movimientos = MovimientoCaja.query.filter_by(
            id_sesion_caja=self.sesion.id_sesion,
            referencia_tipo='venta',
            referencia_id=venta.id_venta,
        ).all()
        self.assertEqual(len(movimientos), 1)
        self.assertEqual(movimientos[0].tipo, 'ingreso')
        self.assertAlmostEqual(float(movimientos[0].monto or 0), 20000.0)

    def test_contabilidad_separa_venta_emitida_cobro_y_saldo_financiado_en_credito(self):
        from app.models import Cliente, Configuracion
        from app.routes.caja.contabilidad_report import calcular_informe_contable_rango
        from app.utils.helpers import today_local, utc_bounds_for_local_dates
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

        producto = self._crear_producto_simple('TEST-CONTAB-CREDITO-001', 100000)
        cliente_credito = Cliente(
            nombre='Cliente Contabilidad Credito',
            ruc_ci='8000099-9',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(cliente_credito)
        db.session.commit()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [
                    {'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 20000},
                    {'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 80000},
                ],
                'id_cliente': int(cliente_credito.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-contabilidad-credito-001',
            },
        )
        self.assertEqual(resp.status_code, 200)
        venta_id = int((resp.get_json() or {})['id_venta'])

        start_utc, end_utc = utc_bounds_for_local_dates(today_local(), today_local())
        informe = calcular_informe_contable_rango(start_utc, end_utc)

        self.assertAlmostEqual(float(informe.get('ventas_emitidas') or 0), 100000.0)
        self.assertAlmostEqual(float(informe.get('cobrado_en_ventas') or 0), 20000.0)
        self.assertAlmostEqual(float(informe.get('saldo_financiado_generado') or 0), 80000.0)
        self.assertAlmostEqual(float(informe.get('total_cobros_creditos') or 0), 0.0)
        self.assertAlmostEqual(float(informe.get('ganancia_neta_mes') or 0), 100000.0)

        detalle_emitida = next(
            (row for row in (informe.get('detalles') or []) if row.get('concepto') == 'Venta Emitida' and row.get('referencia') == f'Venta #{venta_id}'),
            None,
        )
        self.assertIsNotNone(detalle_emitida)
        self.assertIn('Tipo: Credito', detalle_emitida.get('detalle') or '')
        self.assertIn('Saldo financiado', detalle_emitida.get('detalle') or '')

    def test_contabilidad_no_duplica_cobro_credito_efectivo_como_ingreso_manual(self):
        from app.models import Cliente, Configuracion, CuentaPorCobrar, MovimientoCaja
        from app.routes.caja.contabilidad_report import calcular_informe_contable_rango
        from app.utils.helpers import today_local, utc_bounds_for_local_dates
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO
        from cobranzas.services.cobranza_service import registrar_cobro_credito

        producto = self._crear_producto_simple('TEST-CONTAB-COBRO-CRED-001', 90000)
        cliente_credito = Cliente(
            nombre='Cliente Cobro Credito Contabilidad',
            ruc_ci='8000199-9',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(cliente_credito)
        db.session.commit()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 90000}],
                'id_cliente': int(cliente_credito.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-contabilidad-cobro-credito-001',
            },
        )
        self.assertEqual(resp.status_code, 200)
        venta_id = int((resp.get_json() or {})['id_venta'])
        cuenta = CuentaPorCobrar.query.filter_by(id_venta=venta_id).first()
        self.assertIsNotNone(cuenta)

        registrar_cobro_credito(
            cuenta,
            id_usuario=int(self.admin.id_usuario),
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=30000,
            sesion=self.sesion,
        )
        db.session.commit()
        self.assertEqual(MovimientoCaja.query.filter_by(referencia_tipo='cobro_credito').count(), 1)

        start_utc, end_utc = utc_bounds_for_local_dates(today_local(), today_local())
        informe = calcular_informe_contable_rango(start_utc, end_utc)

        self.assertAlmostEqual(float(informe.get('total_cobros_creditos') or 0), 30000.0)
        self.assertAlmostEqual(float(informe.get('ingresos_manuales') or 0), 0.0)
        self.assertAlmostEqual(float(informe.get('total_ingresos') or 0), 30000.0)

        cobros_credito = [row for row in informe.get('detalles') or [] if row.get('concepto') == 'Cobro de Crédito']
        self.assertEqual(len(cobros_credito), 1)
        self.assertAlmostEqual(float(cobros_credito[0].get('entrada') or 0), 30000.0)

    def test_detalle_venta_credito_muestra_tipo_y_saldo_pendiente(self):
        from app.models import Cliente, Configuracion
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

        producto = self._crear_producto_simple('TEST-DETALLE-CREDITO-001', 85000)
        cliente_credito = Cliente(
            nombre='Cliente Detalle Credito',
            ruc_ci='8000100-0',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(cliente_credito)
        db.session.commit()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 85000}],
                'id_cliente': int(cliente_credito.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-detalle-credito-001',
            },
        )
        self.assertEqual(resp.status_code, 200)
        venta_id = int((resp.get_json() or {})['id_venta'])

        detalle_resp = self.client.get(f'/ventas/{venta_id}')
        self.assertEqual(detalle_resp.status_code, 200)
        html = detalle_resp.get_data(as_text=True)
        self.assertIn('Tipo de venta', html)
        self.assertIn('Credito', html)
        self.assertIn('Saldo pendiente', html)
        self.assertIn('85.000', html)

    def test_reporte_detalle_venta_expone_tipo_cobro_y_saldo_en_credito(self):
        from app.models import Cliente, Configuracion
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

        producto = self._crear_producto_simple('TEST-REPORTE-DETALLE-CRED-001', 100000)
        cliente_credito = Cliente(
            nombre='Cliente Reporte Credito',
            ruc_ci='8000101-1',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(cliente_credito)
        db.session.commit()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [
                    {'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 30000},
                    {'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 70000},
                ],
                'id_cliente': int(cliente_credito.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-reporte-detalle-credito-001',
            },
        )
        self.assertEqual(resp.status_code, 200)
        venta_id = int((resp.get_json() or {})['id_venta'])

        detalle_resp = self.client.get(f'/reportes/ventas/{venta_id}/detalle')
        self.assertEqual(detalle_resp.status_code, 200)
        data = detalle_resp.get_json() or {}
        self.assertEqual(data.get('tipo_venta'), 'Credito')
        self.assertEqual(data.get('estado_cobro'), 'Parcial')
        self.assertAlmostEqual(float(data.get('cobrado_al_momento') or 0), 30000.0)
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 70000.0)

    def test_reporte_detalle_venta_incluye_cobros_posteriores_de_credito(self):
        from app.models import Cliente, Configuracion, CuentaPorCobrar
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO
        from cobranzas.services.cobranza_service import registrar_cobro_credito

        producto = self._crear_producto_simple('TEST-REPORTE-DETALLE-COBRO-POST-001', 90000)
        cliente_credito = Cliente(
            nombre='Cliente Cobro Posterior',
            ruc_ci='8000101-9',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(cliente_credito)
        db.session.commit()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 90000}],
                'id_cliente': int(cliente_credito.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-reporte-detalle-cobro-posterior-001',
            },
        )
        self.assertEqual(resp.status_code, 200)
        venta_id = int((resp.get_json() or {})['id_venta'])

        cuenta = CuentaPorCobrar.query.filter_by(id_venta=venta_id).first()
        self.assertIsNotNone(cuenta)

        registrar_cobro_credito(
            cuenta,
            id_usuario=int(self.admin.id_usuario),
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=90000,
            sesion=self.sesion,
        )
        db.session.commit()

        detalle_resp = self.client.get(f'/reportes/ventas/{venta_id}/detalle')
        self.assertEqual(detalle_resp.status_code, 200)
        data = detalle_resp.get_json() or {}

        self.assertEqual(data.get('estado_cobro'), 'Pagada')
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 0.0)
        self.assertEqual(len(data.get('pagos') or []), 1)
        self.assertEqual(data['pagos'][0].get('metodo'), self.metodo_efectivo.nombre)
        self.assertEqual(data['pagos'][0].get('origen'), 'cobranza')
        self.assertAlmostEqual(float(data['pagos'][0].get('monto') or 0), 90000.0)

    def test_cobro_posterior_parcial_marca_estado_parcial_en_detalle_y_reportes(self):
        from app.models import Cliente, Configuracion, CuentaPorCobrar
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO
        from cobranzas.services.cobranza_service import registrar_cobro_credito

        producto = self._crear_producto_simple('TEST-REPORTE-DETALLE-COBRO-PARCIAL-001', 90000)
        cliente_credito = Cliente(
            nombre='Cliente Cobro Parcial Posterior',
            ruc_ci='8000101-8',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(cliente_credito)
        db.session.commit()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 90000}],
                'id_cliente': int(cliente_credito.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-reporte-detalle-cobro-parcial-001',
            },
        )
        self.assertEqual(resp.status_code, 200)
        venta_id = int((resp.get_json() or {})['id_venta'])

        cuenta = CuentaPorCobrar.query.filter_by(id_venta=venta_id).first()
        self.assertIsNotNone(cuenta)

        registrar_cobro_credito(
            cuenta,
            id_usuario=int(self.admin.id_usuario),
            id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
            monto=30000,
            sesion=self.sesion,
        )
        db.session.commit()

        detalle_reportes_resp = self.client.get(f'/reportes/ventas/{venta_id}/detalle')
        self.assertEqual(detalle_reportes_resp.status_code, 200)
        detalle_reportes = detalle_reportes_resp.get_json() or {}
        self.assertEqual(detalle_reportes.get('estado_cobro'), 'Parcial')
        self.assertAlmostEqual(float(detalle_reportes.get('saldo_pendiente') or 0), 60000.0)

        detalle_venta_resp = self.client.get(f'/ventas/{venta_id}')
        self.assertEqual(detalle_venta_resp.status_code, 200)
        html = detalle_venta_resp.get_data(as_text=True)
        self.assertIn('Estado de cobro', html)
        self.assertIn('Parcial', html)

    def test_estado_caja_resume_creditos_separado_de_cobros_en_ventas(self):
        from app.models import Cliente, Configuracion, CuentaPorCobrar, PagoCuentaCobrar
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

        producto = self._crear_producto_simple('TEST-ESTADO-CAJA-CRED-001', 90000)
        cliente_credito = Cliente(
            nombre='Cliente Estado Caja Credito',
            ruc_ci='8000102-2',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(cliente_credito)
        db.session.commit()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [
                    {'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 10000},
                    {'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 80000},
                ],
                'id_cliente': int(cliente_credito.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-estado-caja-credito-001',
            },
        )
        self.assertEqual(resp.status_code, 200)
        venta_id = int((resp.get_json() or {})['id_venta'])
        cuenta = CuentaPorCobrar.query.filter_by(id_venta=venta_id).first()
        self.assertIsNotNone(cuenta)

        db.session.add(
            PagoCuentaCobrar(
                id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar),
                id_sesion_caja=int(self.sesion.id_sesion),
                id_usuario=int(self.admin.id_usuario),
                monto=25000,
                id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
                referencia='REC-ESTADO-001',
                estado='activo',
            )
        )
        db.session.commit()

        resumen_resp = self.client.get('/caja/api/estado/resumen')
        self.assertEqual(resumen_resp.status_code, 200)
        data = resumen_resp.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertAlmostEqual(float(data.get('total_cobrado_ventas_sesion') or 0), 10000.0)
        self.assertAlmostEqual(float(data.get('total_cobros_creditos_sesion') or 0), 25000.0)
        self.assertAlmostEqual(float(data.get('total_neto_sesion') or 0), 35000.0)

    def test_venta_credito_sigue_funcionando_si_metodo_renombrado_pero_configurado_por_id(self):
        from app.models import Cliente, Configuracion, CuentaPorCobrar, Venta
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO, CLAVE_VENTAS_CREDITO_METODO_PAGO_ID

        producto = self._crear_producto_simple('TEST-CREDITO-RENOMBRE-001', 75000)
        cliente_credito = Cliente(
            nombre='Cliente Credito Renombrado',
            ruc_ci='8000004-4',
            tipo='minorista',
            limite_credito=200000,
            activo=True,
        )
        db.session.add(cliente_credito)
        db.session.commit()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)
        Configuracion.establecer(CLAVE_VENTAS_CREDITO_METODO_PAGO_ID, str(int(self.metodo_credito.id_metodo_pago)))
        self.metodo_credito.nombre = 'Financiacion Interna'
        db.session.commit()

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 75000}],
                'id_cliente': int(cliente_credito.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-credito-renombrado-001',
            },
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get('tipo_venta'), 'credito')
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 75000.0)

        venta = db.session.get(Venta, int(data['id_venta']))
        self.assertIsNotNone(venta)
        self.assertEqual((venta.tipo_venta or '').strip().lower(), 'credito')
        cuenta = CuentaPorCobrar.query.filter_by(id_venta=venta.id_venta).first()
        self.assertIsNotNone(cuenta)

    def test_venta_credito_rechaza_monto_credito_que_supera_saldo_a_financiar(self):
        from app.models import Configuracion, Venta
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

        producto = self._crear_producto_simple('TEST-CREDITO-EXCESO-001', 100000)
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        resp = self._procesar_venta(
            producto,
            [
                {'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 30000},
                {'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 80000},
            ],
            'venta-credito-exceso-001',
        )

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertIn('supera', (data.get('error') or '').lower())
        self.assertIsNone(Venta.query.filter_by(client_request_id='venta-credito-exceso-001').first())

    def test_venta_credito_respeta_precio_minorista_si_pos_desactiva_mayorista(self):
        from app.models import Cliente, Configuracion, CuentaPorCobrar, Venta
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

        producto = self._crear_producto_simple('TEST-CREDITO-MAYO-OFF-001', 50000)
        producto.precio_mayorista = 30000
        db.session.add(producto)

        cliente_mayorista = Cliente(
            nombre='Cliente Mayorista Precio Minorista',
            ruc_ci='8000003-3',
            tipo='mayorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(cliente_mayorista)
        db.session.commit()
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        resp = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [
                    {'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 10000},
                    {'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 40000},
                ],
                'id_cliente': int(cliente_mayorista.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'usar_precio_mayorista': False,
                'client_request_id': 'venta-credito-mayorista-minorista-001',
            },
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertEqual(data.get('tipo_venta'), 'credito')
        self.assertAlmostEqual(float(data.get('pagado') or 0), 10000.0)
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 40000.0)

        venta = db.session.get(Venta, int(data['id_venta']))
        self.assertAlmostEqual(float(venta.total or 0), 50000.0)
        self.assertAlmostEqual(float(venta.saldo_pendiente or 0), 40000.0)

        cuenta = CuentaPorCobrar.query.filter_by(id_venta=venta.id_venta).first()
        self.assertIsNotNone(cuenta)
        self.assertAlmostEqual(float(cuenta.saldo_pendiente or 0), 40000.0)

    def test_venta_contado_efectivo_genera_pago_y_movimiento_ingreso(self):
        from app.models import MovimientoCaja, PagoVenta, Venta

        producto = self._crear_producto_simple('TEST-CONTADO-EFEC-001', 75000)
        resp = self._procesar_venta(
            producto,
            [{
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 75000,
            }],
            'venta-contado-efectivo-001',
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get('success'))
        venta_id = int(data['id_venta'])

        venta = db.session.get(Venta, venta_id)
        self.assertIsNotNone(venta)

        pagos = PagoVenta.query.filter_by(id_venta=venta_id).all()
        self.assertEqual(len(pagos), 1)
        self.assertEqual(int(pagos[0].id_metodo_pago), int(self.metodo_efectivo.id_metodo_pago))
        self.assertAlmostEqual(float(pagos[0].monto or 0), 75000.0)

        movimientos = MovimientoCaja.query.filter_by(
            id_sesion_caja=self.sesion.id_sesion,
            referencia_tipo='venta',
            referencia_id=venta_id,
        ).all()
        self.assertEqual(len(movimientos), 1)
        self.assertEqual(movimientos[0].tipo, 'ingreso')
        self.assertAlmostEqual(float(movimientos[0].monto or 0), 75000.0)
        self.assertAlmostEqual(float(self.sesion.calcular_total_efectivo() or 0), 575000.0)

    def test_venta_contado_con_vuelto_genera_movimiento_egreso(self):
        from app.models import MovimientoCaja

        producto = self._crear_producto_simple('TEST-CONTADO-VUELTO-001', 75000)
        resp = self._procesar_venta(
            producto,
            [{
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 100000,
            }],
            'venta-contado-vuelto-001',
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertAlmostEqual(float(data.get('vuelto') or 0), 25000.0)

        movimientos = (
            MovimientoCaja.query
            .filter(
                MovimientoCaja.id_sesion_caja == self.sesion.id_sesion,
                MovimientoCaja.referencia_id == int(data['id_venta']),
                MovimientoCaja.referencia_tipo.in_(['venta', 'vuelto']),
            )
            .order_by(MovimientoCaja.id_movimiento_caja.asc())
            .all()
        )
        self.assertEqual(len(movimientos), 2)
        self.assertEqual([mov.tipo for mov in movimientos], ['ingreso', 'egreso'])
        self.assertEqual([mov.referencia_tipo for mov in movimientos], ['venta', 'vuelto'])
        self.assertAlmostEqual(float(movimientos[0].monto or 0), 100000.0)
        self.assertAlmostEqual(float(movimientos[1].monto or 0), 25000.0)
        self.assertAlmostEqual(float(self.sesion.calcular_total_efectivo() or 0), 575000.0)

    def test_venta_contado_admite_vuelto_mixto_si_exceso_es_efectivo(self):
        from app.models import MovimientoCaja, PagoVenta

        producto = self._crear_producto_simple('TEST-CONTADO-VUELTO-MIXTO-001', 120000)
        resp = self._procesar_venta(
            producto,
            [
                {
                    'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                    'monto': 120000,
                },
                {
                    'id_metodo_pago': int(self.metodo_no_efectivo.id_metodo_pago),
                    'monto': 15000,
                },
            ],
            'venta-contado-vuelto-mixto-001',
        )

        self.assertEqual(resp.status_code, 200, resp.get_json())
        data = resp.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertAlmostEqual(float(data.get('vuelto') or 0), 15000.0)
        venta_id = int(data['id_venta'])

        pagos = PagoVenta.query.filter_by(id_venta=venta_id).order_by(PagoVenta.id_pago.asc()).all()
        self.assertEqual(len(pagos), 2)
        self.assertAlmostEqual(sum(float(p.monto or 0) for p in pagos), 135000.0)

        movimientos = (
            MovimientoCaja.query
            .filter_by(id_sesion_caja=self.sesion.id_sesion, referencia_id=venta_id)
            .order_by(MovimientoCaja.id_movimiento_caja.asc())
            .all()
        )
        self.assertEqual([mov.tipo for mov in movimientos], ['ingreso', 'egreso'])
        self.assertEqual([mov.referencia_tipo for mov in movimientos], ['venta', 'vuelto'])
        self.assertAlmostEqual(float(movimientos[0].monto or 0), 120000.0)
        self.assertAlmostEqual(float(movimientos[1].monto or 0), 15000.0)
        self.assertAlmostEqual(float(self.sesion.calcular_total_efectivo() or 0), 605000.0)

    def test_venta_contado_rechaza_vuelto_sin_efectivo(self):
        from app.models import MovimientoCaja, Venta

        producto = self._crear_producto_simple('TEST-CONTADO-VUELTO-NO-EFECTIVO-001', 120000)
        resp = self._procesar_venta(
            producto,
            [{
                'id_metodo_pago': int(self.metodo_no_efectivo.id_metodo_pago),
                'monto': 135000,
            }],
            'venta-contado-vuelto-no-efectivo-001',
        )

        self.assertEqual(resp.status_code, 400)
        data = resp.get_json() or {}
        self.assertIn('efectivo', (data.get('error') or '').lower())
        self.assertIsNone(Venta.query.filter_by(client_request_id='venta-contado-vuelto-no-efectivo-001').first())
        self.assertEqual(MovimientoCaja.query.filter_by(id_sesion_caja=self.sesion.id_sesion).count(), 0)

    def test_venta_contado_no_efectivo_no_genera_movimiento_caja(self):
        from app.models import MovimientoCaja, PagoVenta

        producto = self._crear_producto_simple('TEST-CONTADO-TARJ-001', 88000)
        resp = self._procesar_venta(
            producto,
            [{
                'id_metodo_pago': int(self.metodo_no_efectivo.id_metodo_pago),
                'monto': 88000,
            }],
            'venta-contado-no-efectivo-001',
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get('success'))
        venta_id = int(data['id_venta'])

        pagos = PagoVenta.query.filter_by(id_venta=venta_id).all()
        self.assertEqual(len(pagos), 1)
        self.assertEqual(int(pagos[0].id_metodo_pago), int(self.metodo_no_efectivo.id_metodo_pago))

        movimientos = MovimientoCaja.query.filter_by(
            id_sesion_caja=self.sesion.id_sesion,
            referencia_tipo='venta',
            referencia_id=venta_id,
        ).all()
        self.assertEqual(movimientos, [])
        self.assertAlmostEqual(float(self.sesion.calcular_total_efectivo() or 0), 500000.0)

    def test_calcular_total_efectivo_mantiene_mezcla_actual_de_pagos_y_movimientos(self):
        from app.models import MovimientoCaja

        producto_efectivo = self._crear_producto_simple('TEST-MEZCLA-EFEC-001', 50000)
        producto_no_efectivo = self._crear_producto_simple('TEST-MEZCLA-NOEF-001', 80000)

        resp_efectivo = self._procesar_venta(
            producto_efectivo,
            [{
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 50000,
            }],
            'venta-mezcla-efectivo-001',
        )
        self.assertEqual(resp_efectivo.status_code, 200)

        resp_no_efectivo = self._procesar_venta(
            producto_no_efectivo,
            [{
                'id_metodo_pago': int(self.metodo_no_efectivo.id_metodo_pago),
                'monto': 80000,
            }],
            'venta-mezcla-no-efectivo-001',
        )
        self.assertEqual(resp_no_efectivo.status_code, 200)

        db.session.add(MovimientoCaja(
            id_sesion_caja=self.sesion.id_sesion,
            id_usuario=self.admin.id_usuario,
            tipo='ingreso',
            monto=10000,
            motivo='Ingreso manual test',
            referencia_tipo='ajuste_manual',
            referencia_id=1,
        ))
        db.session.add(MovimientoCaja(
            id_sesion_caja=self.sesion.id_sesion,
            id_usuario=self.admin.id_usuario,
            tipo='egreso',
            monto=5000,
            motivo='Egreso manual test',
            referencia_tipo='ajuste_manual',
            referencia_id=2,
        ))
        db.session.commit()

        self.assertAlmostEqual(float(self.sesion.calcular_total_efectivo() or 0), 555000.0)


if __name__ == '__main__':
    unittest.main()
