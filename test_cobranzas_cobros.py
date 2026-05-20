import unittest

from app import create_app, db
from sqlalchemy import update


class TestCobranzasCobros(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, MetodoPago, SesionCaja, Usuario
        from cobranzas import CLAVE_COBRANZAS_ACTIVO, CLAVE_VENTAS_CREDITO_ACTIVO

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.assertIsNotNone(self.metodo_efectivo)

        self.metodo_credito = MetodoPago.query.filter(MetodoPago.nombre.ilike('%Crédito Tienda%')).first()
        self.assertIsNotNone(self.metodo_credito)

        self.metodo_con_referencia = (
            MetodoPago.query
            .filter(
                MetodoPago.activo.is_(True),
                MetodoPago.requiere_referencia.is_(True),
                MetodoPago.id_metodo_pago != self.metodo_credito.id_metodo_pago,
            )
            .order_by(MetodoPago.orden_display.asc(), MetodoPago.id_metodo_pago.asc())
            .first()
        )
        self.assertIsNotNone(self.metodo_con_referencia)

        self.metodo_no_efectivo = (
            MetodoPago.query
            .filter(MetodoPago.activo.is_(True), MetodoPago.id_metodo_pago.notin_([self.metodo_efectivo.id_metodo_pago, self.metodo_credito.id_metodo_pago]))
            .order_by(MetodoPago.orden_display.asc(), MetodoPago.id_metodo_pago.asc())
            .first()
        )
        self.assertIsNotNone(self.metodo_no_efectivo)

        self.cliente = Cliente(
            nombre='Cliente Cobranza Test',
            ruc_ci='9000001-1',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(self.cliente)
        db.session.commit()

        self.consumidor_final = db.session.get(Cliente, 1)
        if self.consumidor_final is None:
            self.consumidor_final = Cliente(
                id_cliente=1,
                nombre='Consumidor Final',
                tipo='minorista',
                activo=True,
            )
            db.session.add(self.consumidor_final)
            db.session.commit()

        self.sesion = SesionCaja(
            id_caja=1,
            id_usuario=self.admin.id_usuario,
            monto_inicial=300000,
            estado='abierta',
        )
        db.session.add(self.sesion)
        db.session.commit()

        from app.models import Configuracion

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

        categoria = Categoria.query.filter_by(nombre='Test Cobranzas').first()
        if categoria is None:
            categoria = Categoria(nombre='Test Cobranzas', activo=True)
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

    def _crear_venta_credito(self, codigo, precio, pagos, request_id):
        from app.models import CuentaPorCobrar

        producto = self._crear_producto_simple(codigo, precio)
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': pagos,
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

    def _crear_reparacion_simple(self):
        from app.models import Reparacion

        reparacion = Reparacion(
            cliente_id=int(self.cliente.id_cliente),
            id_usuario_vendedor=int(self.admin.id_usuario),
            tipo_equipo='Celular',
            marca_modelo='Equipo Test',
            falla_reportada='No enciende',
            estado='pendiente',
        )
        db.session.add(reparacion)
        db.session.commit()
        return reparacion

    def _crear_pendiente_caja_venta(self, producto, request_id):
        from app.models import ColaCobro

        pendiente = ColaCobro(
            tipo_origen='venta',
            id_origen=None,
            id_cliente=int(self.cliente.id_cliente),
            monto_total=float(producto.precio_venta),
            id_usuario_origen=int(self.admin.id_usuario),
            id_usuario_destino=int(self.admin.id_usuario),
            estado='en_proceso',
        )
        pendiente.set_metadata({
            'client_request_id': request_id,
            'id_usuario_vendedor': int(self.admin.id_usuario),
            'descuento': 0,
            'observaciones': '',
            'items': [{
                'id': int(producto.id_producto),
                'codigo': producto.codigo,
                'nombre': producto.nombre,
                'precio': float(producto.precio_venta),
                'precio_base': float(producto.precio_venta),
                'precio_mayorista': float(getattr(producto, 'precio_mayorista', 0) or 0),
                'cantidad': 1,
                'es_servicio': False,
                'stock': int(producto.stock_actual or 0),
                'stock_minimo': int(producto.stock_minimo or 0),
                'iva': int(producto.porcentaje_iva or 0),
                'precio_manual': False,
                'precio_opcion_id': None,
            }],
        })
        db.session.add(pendiente)
        db.session.commit()
        return pendiente

    def _crear_usuario_con_permisos(self, username, codigos_permisos):
        from app.models import Permiso, Rol, Usuario

        rol = Rol(
            nombre=f'Rol {username}',
            descripcion=f'Rol de pruebas para {username}',
            nivel_jerarquia=5,
            activo=True,
        )
        permisos = Permiso.query.filter(Permiso.codigo.in_(list(codigos_permisos))).all()
        for permiso in permisos:
            rol.permisos.append(permiso)
        db.session.add(rol)
        db.session.flush()

        usuario = Usuario(
            username=username,
            nombre_completo=f'Usuario {username}',
            id_rol=int(rol.id_rol),
            activo=True,
        )
        usuario.set_password('test123')
        db.session.add(usuario)
        db.session.commit()
        return usuario

    def test_cobro_credito_efectivo_actualiza_saldos_y_genera_movimiento(self):
        from app.models import Cliente, MovimientoCaja, PagoCuentaCobrar, Venta

        _, cuenta = self._crear_venta_credito(
            'TEST-COBRO-CRED-EF-001',
            100000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 100000}],
            'venta-credito-cobro-efectivo-001',
        )

        response = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 40000,
                'referencia': 'REC-001',
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 60000.0)
        self.assertEqual((data.get('tipo_venta') or '').strip().lower(), 'credito')

        pago = db.session.get(PagoCuentaCobrar, int(data['id_pago_cuenta']))
        self.assertIsNotNone(pago)
        self.assertAlmostEqual(float(pago.monto or 0), 40000.0)

        movimiento = db.session.get(MovimientoCaja, int(data['movimiento_caja_id']))
        self.assertIsNotNone(movimiento)
        self.assertEqual(movimiento.tipo, 'ingreso')
        self.assertEqual((movimiento.referencia_tipo or '').strip().lower(), 'cobro_credito')
        self.assertAlmostEqual(float(movimiento.monto or 0), 40000.0)

        cuenta_db = db.session.get(type(cuenta), int(cuenta.id_cuenta_cobrar))
        self.assertAlmostEqual(float(cuenta_db.monto_cobrado or 0), 40000.0)
        self.assertAlmostEqual(float(cuenta_db.saldo_pendiente or 0), 60000.0)

        venta = db.session.get(Venta, int(cuenta.id_venta))
        self.assertEqual((venta.tipo_venta or '').strip().lower(), 'credito')
        self.assertAlmostEqual(float(venta.saldo_pendiente or 0), 60000.0)

        cliente = db.session.get(Cliente, int(self.cliente.id_cliente))
        self.assertAlmostEqual(float(cliente.saldo_pendiente or 0), 60000.0)

    def test_cobro_credito_no_efectivo_no_genera_movimiento_caja(self):
        from app.models import MovimientoCaja, PagoCuentaCobrar

        _, cuenta = self._crear_venta_credito(
            'TEST-COBRO-CRED-TRJ-001',
            70000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 70000}],
            'venta-credito-cobro-tarjeta-001',
        )

        response = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_no_efectivo.id_metodo_pago),
                'monto': 20000,
                'referencia': 'REF-NO-EFECTIVO-001',
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertIsNone(data.get('movimiento_caja_id'))
        self.assertEqual(PagoCuentaCobrar.query.filter_by(id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar)).count(), 1)
        self.assertEqual(
            MovimientoCaja.query.filter_by(referencia_tipo='cobro_credito', referencia_id=int(data['id_pago_cuenta'])).count(),
            0,
        )

    def test_cobro_credito_total_deja_cuenta_pagada_y_venta_sigue_credito(self):
        from app.models import Cliente, Venta

        _, cuenta = self._crear_venta_credito(
            'TEST-COBRO-CRED-TOTAL-001',
            50000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 50000}],
            'venta-credito-cobro-total-001',
        )

        response = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 50000,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 0.0)
        self.assertEqual((data.get('estado_cuenta') or '').strip().lower(), 'pagada')

        cuenta_db = db.session.get(type(cuenta), int(cuenta.id_cuenta_cobrar))
        self.assertEqual((cuenta_db.estado or '').strip().lower(), 'pagada')

        venta = db.session.get(Venta, int(cuenta.id_venta))
        self.assertEqual((venta.tipo_venta or '').strip().lower(), 'credito')
        self.assertAlmostEqual(float(venta.saldo_pendiente or 0), 0.0)

        cliente = db.session.get(Cliente, int(self.cliente.id_cliente))
        self.assertAlmostEqual(float(cliente.saldo_pendiente or 0), 0.0)

    def test_cobro_credito_rechaza_monto_mayor_al_saldo(self):
        from app.models import PagoCuentaCobrar

        _, cuenta = self._crear_venta_credito(
            'TEST-COBRO-CRED-ERR-001',
            60000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 60000}],
            'venta-credito-cobro-error-001',
        )

        response = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 70000,
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        self.assertIn('saldo', (data.get('mensaje') or '').lower())
        self.assertEqual(PagoCuentaCobrar.query.filter_by(id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar)).count(), 0)

    def test_cobro_credito_rechaza_usar_metodo_credito_tienda(self):
        from app.models import PagoCuentaCobrar

        _, cuenta = self._crear_venta_credito(
            'TEST-COBRO-CRED-METODO-001',
            65000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 65000}],
            'venta-credito-metodo-cobro-invalido-001',
        )

        response = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_credito.id_metodo_pago),
                'monto': 10000,
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        mensaje = (data.get('mensaje') or '').lower()
        self.assertIn('cobro', mensaje)
        self.assertIn('tienda', mensaje)
        self.assertEqual(PagoCuentaCobrar.query.filter_by(id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar)).count(), 0)

    def test_cobro_credito_rechaza_falta_referencia_si_metodo_la_exige(self):
        from app.models import PagoCuentaCobrar

        _, cuenta = self._crear_venta_credito(
            'TEST-COBRO-CRED-REF-001',
            65000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 65000}],
            'venta-credito-cobro-sin-referencia-001',
        )

        response = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_con_referencia.id_metodo_pago),
                'monto': 10000,
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        mensaje = (data.get('mensaje') or '').lower()
        self.assertIn('requiere referencia', mensaje)
        self.assertEqual(PagoCuentaCobrar.query.filter_by(id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar)).count(), 0)

    def test_cobro_credito_rechaza_metodo_credito_renombrado_si_sigue_configurado_por_id(self):
        from app.models import Configuracion, PagoCuentaCobrar
        from cobranzas import CLAVE_VENTAS_CREDITO_METODO_PAGO_ID

        Configuracion.establecer(CLAVE_VENTAS_CREDITO_METODO_PAGO_ID, str(int(self.metodo_credito.id_metodo_pago)))
        self.metodo_credito.nombre = 'Financiacion Interna'
        db.session.commit()

        _, cuenta = self._crear_venta_credito(
            'TEST-COBRO-CRED-METODO-REN-001',
            65000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 65000}],
            'venta-credito-metodo-cobro-renombrado-001',
        )

        response = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_credito.id_metodo_pago),
                'monto': 10000,
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        mensaje = (data.get('mensaje') or '').lower()
        self.assertIn('cobro', mensaje)
        self.assertEqual(PagoCuentaCobrar.query.filter_by(id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar)).count(), 0)

    def test_registrar_cobro_credito_revalida_saldo_con_cuenta_recargada(self):
        from app.models import CuentaPorCobrar, PagoCuentaCobrar
        from cobranzas.services.cobranza_service import registrar_cobro_credito

        _, cuenta = self._crear_venta_credito(
            'TEST-COBRO-CRED-STALE-001',
            60000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 60000}],
            'venta-credito-cobro-stale-001',
        )
        cuenta_stale = db.session.get(CuentaPorCobrar, int(cuenta.id_cuenta_cobrar))
        self.assertAlmostEqual(float(cuenta_stale.saldo_pendiente or 0), 60000.0)

        with db.engine.begin() as conn:
            conn.execute(
                update(CuentaPorCobrar)
                .where(CuentaPorCobrar.id_cuenta_cobrar == int(cuenta.id_cuenta_cobrar))
                .values(monto_cobrado=40000, saldo_pendiente=20000)
            )

        with self.assertRaises(ValueError) as exc:
            registrar_cobro_credito(
                cuenta_stale,
                id_usuario=int(self.admin.id_usuario),
                id_metodo_pago=int(self.metodo_efectivo.id_metodo_pago),
                monto=30000,
                sesion=self.sesion,
            )

        self.assertIn('saldo', str(exc.exception).lower())
        self.assertEqual(PagoCuentaCobrar.query.filter_by(id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar)).count(), 0)

    def test_ficha_cuenta_sin_plan_prefill_con_saldo_total(self):
        _, cuenta = self._crear_venta_credito(
            'TEST-COBRO-CRED-FICHA-001',
            60000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 60000}],
            'venta-credito-ficha-libre-001',
        )

        response = self.client.get(f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('value="60000.0"', html)
        self.assertIn('saldo pendiente total de la cuenta', html.lower())

    def test_ficha_cuenta_permite_cobrador_sin_ver_cobranzas(self):
        usuario = self._crear_usuario_con_permisos(
            'cobrador_credito_test',
            {'registrar_cobro_credito'},
        )
        self.assertFalse(usuario.tiene_permiso('ver_cobranzas'))
        self.assertTrue(usuario.tiene_permiso('registrar_cobro_credito'))

        _, cuenta = self._crear_venta_credito(
            'TEST-COBRO-CRED-PERM-001',
            60000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 60000}],
            'venta-credito-cobrador-permiso-001',
        )

        client_cobrador = self.app.test_client()
        with client_cobrador.session_transaction() as sess:
            sess['_user_id'] = str(usuario.id_usuario)
            sess['_fresh'] = True

        response = client_cobrador.get(f'/cobranzas/cuentas/{int(cuenta.id_cuenta_cobrar)}')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Registrar cobro', html)
        self.assertNotIn('CrÃ©dito Tienda', html)

    def test_anular_cobro_credito_efectivo_revierte_saldos_y_genera_egreso(self):
        from app.models import Cliente, MovimientoCaja, PagoCuentaCobrar, Venta

        _, cuenta = self._crear_venta_credito(
            'TEST-ANULAR-COBRO-EF-001',
            100000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 100000}],
            'venta-credito-anular-cobro-efectivo-001',
        )

        cobro = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 40000,
                'referencia': 'REC-ANULAR-001',
            },
        )
        self.assertEqual(cobro.status_code, 200)
        cobro_data = cobro.get_json() or {}

        response = self.client.post(
            f'/cobranzas/api/cobros/{int(cobro_data["id_pago_cuenta"] )}/anular',
            json={'motivo_anulacion': 'Cobro cargado por error'},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertEqual((data.get('estado_pago') or '').strip().lower(), 'anulado')
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 100000.0)

        pago = db.session.get(PagoCuentaCobrar, int(cobro_data['id_pago_cuenta']))
        self.assertIsNotNone(pago)
        self.assertEqual((pago.estado or '').strip().lower(), 'anulado')
        self.assertEqual((pago.motivo_anulacion or '').strip(), 'Cobro cargado por error')
        self.assertIsNotNone(pago.fecha_anulacion)
        self.assertEqual(int(pago.id_usuario_anulacion), int(self.admin.id_usuario))

        movimiento_reversa = db.session.get(MovimientoCaja, int(data['movimiento_caja_id']))
        self.assertIsNotNone(movimiento_reversa)
        self.assertEqual(movimiento_reversa.tipo, 'egreso')
        self.assertEqual((movimiento_reversa.referencia_tipo or '').strip().lower(), 'anulacion_cobro_credito')
        self.assertAlmostEqual(float(movimiento_reversa.monto or 0), 40000.0)

        cuenta_db = db.session.get(type(cuenta), int(cuenta.id_cuenta_cobrar))
        self.assertAlmostEqual(float(cuenta_db.monto_cobrado or 0), 0.0)
        self.assertAlmostEqual(float(cuenta_db.saldo_pendiente or 0), 100000.0)
        self.assertEqual((cuenta_db.estado or '').strip().lower(), 'pendiente')

        venta = db.session.get(Venta, int(cuenta.id_venta))
        self.assertEqual((venta.tipo_venta or '').strip().lower(), 'credito')
        self.assertAlmostEqual(float(venta.saldo_pendiente or 0), 100000.0)

        cliente = db.session.get(Cliente, int(self.cliente.id_cliente))
        self.assertAlmostEqual(float(cliente.saldo_pendiente or 0), 100000.0)

    def test_anular_cobro_credito_no_efectivo_no_genera_movimiento(self):
        from app.models import MovimientoCaja, PagoCuentaCobrar

        _, cuenta = self._crear_venta_credito(
            'TEST-ANULAR-COBRO-TRJ-001',
            90000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 90000}],
            'venta-credito-anular-cobro-tarjeta-001',
        )

        cobro = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_no_efectivo.id_metodo_pago),
                'monto': 25000,
                'referencia': 'REF-NO-EFECTIVO-ANULAR-001',
            },
        )
        self.assertEqual(cobro.status_code, 200)
        cobro_data = cobro.get_json() or {}

        response = self.client.post(
            f'/cobranzas/api/cobros/{int(cobro_data["id_pago_cuenta"] )}/anular',
            json={},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertIsNone(data.get('movimiento_caja_id'))
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 90000.0)

        pago = db.session.get(PagoCuentaCobrar, int(cobro_data['id_pago_cuenta']))
        self.assertEqual((pago.estado or '').strip().lower(), 'anulado')
        self.assertIsNone(pago.id_movimiento_reversa)
        self.assertEqual(
            MovimientoCaja.query.filter_by(
                referencia_tipo='anulacion_cobro_credito',
                referencia_id=int(cobro_data['id_pago_cuenta']),
            ).count(),
            0,
        )

    def test_anular_cobro_credito_rechaza_doble_anulacion(self):
        _, cuenta = self._crear_venta_credito(
            'TEST-ANULAR-COBRO-DOBLE-001',
            80000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 80000}],
            'venta-credito-anular-cobro-doble-001',
        )

        cobro = self.client.post(
            f'/cobranzas/api/cuentas/{int(cuenta.id_cuenta_cobrar)}/cobros',
            json={
                'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago),
                'monto': 15000,
            },
        )
        self.assertEqual(cobro.status_code, 200)
        cobro_data = cobro.get_json() or {}

        primera = self.client.post(f'/cobranzas/api/cobros/{int(cobro_data["id_pago_cuenta"] )}/anular', json={})
        self.assertEqual(primera.status_code, 200)

        segunda = self.client.post(f'/cobranzas/api/cobros/{int(cobro_data["id_pago_cuenta"] )}/anular', json={})
        self.assertEqual(segunda.status_code, 400)
        data = segunda.get_json() or {}
        self.assertIn('anulad', (data.get('mensaje') or '').lower())

    def test_venta_credito_rechaza_cliente_consumidor_final(self):
        producto = self._crear_producto_simple('TEST-CRED-CF-001', 30000)

        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 30000}],
                'id_cliente': int(self.consumidor_final.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-credito-consumidor-final-001',
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        self.assertIn('cliente registrado', (data.get('error') or '').lower())

    def test_venta_credito_permite_autorizacion_admin_si_usuario_no_tiene_permiso_directo(self):
        from app.models import Autorizacion, Caja, Configuracion, CuentaPorCobrar, SesionCaja, Venta
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

        usuario = self._crear_usuario_con_permisos('vende_solo_contado', {'crear_venta'})
        producto = self._crear_producto_simple('TEST-CRED-AUTH-001', 55000)
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)
        caja_usuario = Caja(nombre='Caja Usuario Credito Test', ubicacion='Mostrador Secundario', activa=True)
        db.session.add(caja_usuario)
        db.session.flush()
        db.session.add(SesionCaja(
            id_caja=int(caja_usuario.id_caja),
            id_usuario=int(usuario.id_usuario),
            monto_inicial=150000,
            estado='abierta',
        ))
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(usuario.id_usuario)
            sess['_fresh'] = True

        autorizacion = Autorizacion.crear_autorizacion(
            id_solicitante=int(usuario.id_usuario),
            id_autorizador=int(self.admin.id_usuario),
            codigo_permiso='venta_credito',
            accion='Venta a credito de prueba',
        )

        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 55000}],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(usuario.id_usuario),
                'id_autorizacion': int(autorizacion.id_autorizacion),
                'client_request_id': 'venta-credito-autorizada-001',
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        self.assertTrue(data.get('success'))
        venta = Venta.query.filter_by(client_request_id='venta-credito-autorizada-001').first()
        self.assertIsNotNone(venta)
        self.assertEqual((venta.tipo_venta or '').strip().lower(), 'credito')
        self.assertIsNotNone(CuentaPorCobrar.query.filter_by(id_venta=int(venta.id_venta)).first())

    def test_venta_rechaza_id_autorizacion_invalido_con_400(self):
        from app.models import Configuracion, Venta
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

        producto = self._crear_producto_simple('TEST-CRED-AUTH-INVALID-001', 45000)
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 45000}],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'id_autorizacion': 'abc',
                'client_request_id': 'venta-credito-id-autorizacion-invalido-001',
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        self.assertIn('id_autorizacion', (data.get('error') or '').lower())
        self.assertIsNone(Venta.query.filter_by(client_request_id='venta-credito-id-autorizacion-invalido-001').first())

    def test_auditoria_venta_credito_guarda_vuelto_real_en_cero(self):
        from app.models import Auditoria

        producto = self._crear_producto_simple('TEST-CRED-AUD-001', 100000)
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [
                    {'id_metodo_pago': int(self.metodo_efectivo.id_metodo_pago), 'monto': 20000},
                    {'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 80000},
                ],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-credito-auditoria-vuelto-001',
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json() or {}
        auditoria = (
            Auditoria.query
            .filter_by(accion='crear_venta', referencia_tipo='venta', referencia_id=int(data['id_venta']))
            .order_by(Auditoria.id_auditoria.desc())
            .first()
        )
        self.assertIsNotNone(auditoria)
        datos_nuevos = auditoria.get_datos_nuevos() or {}
        self.assertAlmostEqual(float(datos_nuevos.get('total_pagado') or 0), 20000.0)
        self.assertAlmostEqual(float(datos_nuevos.get('vuelto') or 0), 0.0)

    def test_venta_credito_rechaza_si_supera_credito_disponible(self):
        self._crear_venta_credito(
            'TEST-CRED-LIMITE-001',
            450000,
            [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 450000}],
            'venta-credito-limite-001',
        )

        producto = self._crear_producto_simple('TEST-CRED-LIMITE-002', 100000)
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 100000}],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-credito-limite-002',
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        self.assertIn('credito insuficiente', (data.get('error') or '').lower())

    def test_venta_rechaza_metodo_pago_inactivo(self):
        self.metodo_no_efectivo.activo = False
        db.session.commit()
        producto = self._crear_producto_simple('TEST-PAGO-INACTIVO-001', 25000)

        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_no_efectivo.id_metodo_pago), 'monto': 25000}],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-metodo-inactivo-001',
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        self.assertIn('inactivo', (data.get('error') or '').lower())

    def test_venta_credito_rechaza_reparacion_desde_pos(self):
        from app.models import CuentaPorCobrar, Venta

        producto = self._crear_producto_simple('TEST-CRED-REP-001', 55000)
        reparacion = self._crear_reparacion_simple()

        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 55000}],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'reparacion_id': int(reparacion.id_reparacion),
                'client_request_id': 'venta-credito-reparacion-001',
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        self.assertIn('reparaciones', (data.get('error') or '').lower())
        self.assertEqual(Venta.query.count(), 0)
        self.assertEqual(CuentaPorCobrar.query.count(), 0)

    def test_venta_credito_rechaza_pendiente_enviado_a_caja(self):
        from app.models import CuentaPorCobrar, Venta

        producto = self._crear_producto_simple('TEST-CRED-COLA-001', 65000)
        pendiente = self._crear_pendiente_caja_venta(producto, 'pendiente-caja-credito-001')

        response = self.client.post(
            '/ventas/procesar',
            json={
                'cola_cobro_id': int(pendiente.id),
                'pagos': [{'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 65000}],
                'client_request_id': 'venta-credito-cola-001',
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        self.assertIn('pendientes enviados a caja', (data.get('error') or '').lower())
        self.assertEqual(Venta.query.count(), 0)
        self.assertEqual(CuentaPorCobrar.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
