import unittest

from app import create_app, db


class TestVentasCreditoReferencias(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, Configuracion, MetodoPago, SesionCaja, Usuario
        from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.metodo_credito = MetodoPago.query.filter(MetodoPago.nombre.ilike('%tienda%')).first()
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

        self.cliente = Cliente(
            nombre='Cliente Venta Credito Ref',
            ruc_ci='9000099-1',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(self.cliente)
        db.session.commit()

        self.sesion = SesionCaja(
            id_caja=1,
            id_usuario=self.admin.id_usuario,
            monto_inicial=250000,
            estado='abierta',
        )
        db.session.add(self.sesion)
        db.session.commit()

        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _crear_producto_simple(self, codigo='TEST-VENTA-CRED-REF-001', precio=100000):
        from app.models import Categoria, Producto

        categoria = Categoria.query.filter_by(nombre='Test Venta Credito Ref').first()
        if categoria is None:
            categoria = Categoria(nombre='Test Venta Credito Ref', activo=True)
            db.session.add(categoria)
            db.session.flush()

        producto = Producto(
            codigo=codigo,
            nombre=f'Producto {codigo}',
            id_categoria=categoria.id_categoria,
            precio_compra=max(int(precio / 2), 1),
            precio_venta=precio,
            porcentaje_iva=10,
            stock_actual=15,
            stock_minimo=1,
            es_servicio=False,
            activo=True,
        )
        db.session.add(producto)
        db.session.commit()
        return producto

    def test_venta_credito_mixta_rechaza_falta_referencia_si_metodo_la_exige(self):
        from app.models import PagoVenta, Venta

        producto = self._crear_producto_simple()
        response = self.client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [
                    {'id_metodo_pago': int(self.metodo_con_referencia.id_metodo_pago), 'monto': 30000},
                    {'id_metodo_pago': int(self.metodo_credito.id_metodo_pago), 'monto': 70000},
                ],
                'id_cliente': int(self.cliente.id_cliente),
                'id_usuario_vendedor': int(self.admin.id_usuario),
                'client_request_id': 'venta-credito-mixta-sin-referencia-001',
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json() or {}
        self.assertIn('requiere referencia', (data.get('error') or '').lower())
        self.assertIsNone(Venta.query.filter_by(client_request_id='venta-credito-mixta-sin-referencia-001').first())
        self.assertEqual(PagoVenta.query.count(), 0)
