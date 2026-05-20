import re
import unittest

from app import create_app, db


class TestRecepcionUsados(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Categoria, MetodoPago, SesionCaja, Usuario

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.categoria = Categoria.query.filter_by(activo=True).first()
        if self.categoria is None:
            self.categoria = Categoria(nombre='Celulares Usados', activo=True)
            db.session.add(self.categoria)
            db.session.flush()

        self.metodo_efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.metodo_transferencia = MetodoPago.query.filter(MetodoPago.nombre.ilike('%transferencia%')).first()
        if self.metodo_transferencia is None:
            self.metodo_transferencia = MetodoPago.query.filter_by(activo=True).first()

        self.sesion = SesionCaja(id_caja=1, id_usuario=self.admin.id_usuario, monto_inicial=5000000, estado='abierta')
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

    def _csrf_token(self, path: str) -> str:
        html = self.client.get(path).get_data(as_text=True)
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        self.assertIsNotNone(match)
        return match.group(1)

    def _payload_base(self, csrf_token: str) -> dict:
        return {
            'csrf_token': csrf_token,
            'fecha_formulario': '2026-03-12',
            'nombres_apellidos': 'Juan Perez',
            'fecha_nacimiento': '1990-05-10',
            'nacionalidad': 'Paraguaya',
            'tipo_documento': 'Cédula',
            'numero_documento': '1234567',
            'estado_civil': 'Soltero',
            'domicilio': 'Barrio Centro 123',
            'referencia_domicilio': 'Casa azul',
            'barrio': 'Centro',
            'ciudad': 'Ñemby',
            'departamento': 'Central',
            'telefono': '0981123456',
            'descripcion_producto': 'Celular usado en buen estado',
            'id_categoria': str(self.categoria.id_categoria),
            'marca': 'Samsung',
            'modelo': 'A15',
            'color': 'Negro',
            'capacidad': '128GB',
            'imei_serie': 'IMEI123456789',
            'accesorios': 'Caja y cargador',
            'estado_equipo': 'Funciona correctamente',
            'monto_compra': '1500000',
            'referencia_pago': '',
            'domicilio_especial_vendedor': 'Barrio Centro 123',
            'lugar_firma': 'Ñemby',
            'observaciones': 'Sin observaciones',
        }

    def test_registra_compra_usado_con_correlativo_y_caja(self):
        from app.models import Compra, MovimientoCaja, Producto, RecepcionCompraUsado, VendedorUsado

        csrf_token = self._csrf_token('/recepcion-usados/nueva')
        payload = self._payload_base(csrf_token)
        payload['id_metodo_pago'] = str(self.metodo_efectivo.id_metodo_pago)

        resp = self.client.post('/recepcion-usados/nueva', data=payload, follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

        recepcion = RecepcionCompraUsado.query.one()
        vendedor = VendedorUsado.query.one()
        producto = Producto.query.one()
        compra = Compra.query.one()
        movimiento = MovimientoCaja.query.filter_by(
            referencia_tipo='recepcion_compra_usado',
            referencia_id=recepcion.id_recepcion_compra_usado,
        ).first()

        self.assertEqual(recepcion.numero_formulario, 1)
        self.assertEqual(recepcion.numero_formulario_display, '000001')
        self.assertEqual(vendedor.total_ventas_usados, 1)
        self.assertEqual(producto.codigo, 'US-000001')
        self.assertEqual(producto.stock_actual, 1)
        self.assertEqual(compra.numero_factura, 'US-000001')
        self.assertIsNotNone(movimiento)

        print_resp = self.client.get(f'/recepcion-usados/{recepcion.id_recepcion_compra_usado}/imprimir')
        html = print_resp.get_data(as_text=True)
        db.session.refresh(recepcion)
        self.assertEqual(print_resp.status_code, 200)
        self.assertIn('FORMULARIO DE COMPRA DE PRODUCTOS ELECTR', html.upper())
        self.assertEqual(recepcion.cantidad_impresiones, 1)

    def test_reutiliza_vendedor_por_documento_y_no_duplica_registro(self):
        from app.models import MovimientoCaja, RecepcionCompraUsado, VendedorUsado

        csrf_token = self._csrf_token('/recepcion-usados/nueva')
        payload = self._payload_base(csrf_token)
        payload['id_metodo_pago'] = str(self.metodo_efectivo.id_metodo_pago)
        self.client.post('/recepcion-usados/nueva', data=payload, follow_redirects=False)

        csrf_token = self._csrf_token('/recepcion-usados/nueva')
        payload2 = self._payload_base(csrf_token)
        payload2['id_metodo_pago'] = str(self.metodo_transferencia.id_metodo_pago)
        payload2['referencia_pago'] = 'TRX-001'
        payload2['descripcion_producto'] = 'iPhone usado con batería al 90%'
        payload2['marca'] = 'Apple'
        payload2['modelo'] = 'iPhone 13'
        resp = self.client.post('/recepcion-usados/nueva', data=payload2, follow_redirects=False)

        self.assertIn(resp.status_code, (302, 303))
        self.assertEqual(VendedorUsado.query.count(), 1)

        vendedor = VendedorUsado.query.one()
        recepciones = RecepcionCompraUsado.query.order_by(RecepcionCompraUsado.numero_formulario.asc()).all()
        self.assertEqual(vendedor.total_ventas_usados, 2)
        self.assertEqual([r.numero_formulario for r in recepciones], [1, 2])

        movimiento_transfer = MovimientoCaja.query.filter_by(
            referencia_tipo='recepcion_compra_usado',
            referencia_id=recepciones[-1].id_recepcion_compra_usado,
        ).first()
        self.assertIsNone(movimiento_transfer)


if __name__ == '__main__':
    unittest.main()
