import unittest
from decimal import Decimal

from app import create_app, db


class TestPedidosAltaInicial(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Caja, Cliente, MetodoPago, SesionCaja, Usuario

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.cliente = db.session.get(Cliente, 1)
        if self.cliente is None:
            self.cliente = Cliente(nombre='Consumidor Final', tipo='minorista', activo=True)
            db.session.add(self.cliente)
            db.session.commit()

        self.metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.assertIsNotNone(self.metodo_efectivo)

        caja = Caja.query.first()
        if caja is None:
            caja = Caja(nombre='Caja Test', activa=True)
            db.session.add(caja)
            db.session.flush()

        self.sesion = SesionCaja(
            id_caja=int(caja.id_caja),
            id_usuario=int(self.admin.id_usuario),
            monto_inicial=300000,
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

    def _crear_producto_simple(self, codigo='TEST-PED-ALTA-001', precio=120000):
        from app.models import Categoria, Producto

        categoria = Categoria.query.filter_by(nombre='Test Pedidos Alta').first()
        if categoria is None:
            categoria = Categoria(nombre='Test Pedidos Alta', activo=True)
            db.session.add(categoria)
            db.session.flush()

        producto = Producto(
            codigo=codigo,
            nombre=f'Producto {codigo}',
            id_categoria=categoria.id_categoria,
            precio_compra=60000,
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

    def test_parsea_montos_con_separadores_paraguayos(self):
        from pedidos.services.pedido_service import _to_decimal

        self.assertEqual(_to_decimal('100.000'), Decimal('100000'))
        self.assertEqual(_to_decimal('Gs. 1.250.000'), Decimal('1250000'))
        self.assertEqual(_to_decimal('100.000,50'), Decimal('100000.50'))
        self.assertEqual(_to_decimal('100.50'), Decimal('100.50'))

    def test_nuevo_pedido_crea_items_y_pago_inicial(self):
        from pedidos.models import PedidoCliente, PedidoClientePago

        producto = self._crear_producto_simple()
        response = self.client.post(
            '/pedidos/nuevo',
            data={
                'id_cliente': int(self.cliente.id_cliente),
                'observaciones': 'Pedido con carga inicial completa',
                'descuento_monto': '20000',
                'items_id_producto': [str(int(producto.id_producto))],
                'items_cantidad': ['2'],
                'items_precio_unitario': ['120000'],
                'items_observaciones': ['Equipo principal'],
                'tipo_pago_inicial': 'sena',
                'id_metodo_pago_inicial': int(self.metodo_efectivo.id_metodo_pago),
                'monto_pago_inicial': '50000',
                'referencia_pago_inicial': 'SENA-ALTA-001',
                'observaciones_pago_inicial': 'Cobro de seña en alta',
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)

        pedido = PedidoCliente.query.order_by(PedidoCliente.id_pedido.desc()).first()
        self.assertIsNotNone(pedido)
        self.assertEqual(pedido.detalles.count(), 1)
        self.assertAlmostEqual(float(pedido.subtotal or 0), 240000.0)
        self.assertAlmostEqual(float(pedido.total or 0), 220000.0)
        self.assertAlmostEqual(float(pedido.total_pagado or 0), 50000.0)
        self.assertAlmostEqual(float(pedido.saldo_pendiente or 0), 170000.0)
        self.assertEqual((pedido.estado or '').strip(), 'en_preparacion')

        pago = PedidoClientePago.query.filter_by(id_pedido=int(pedido.id_pedido), estado='activo').first()
        self.assertIsNotNone(pago)
        self.assertEqual((pago.tipo_pago or '').strip(), 'sena')
        self.assertEqual((pago.referencia or '').strip(), 'SENA-ALTA-001')


if __name__ == '__main__':
    unittest.main()
