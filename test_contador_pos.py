"""Nº de la factura en papel en el POS: lo propio de este sistema.

- Viaja con la venta enviada a caja: el vendedor lo carga, el cajero cobra el
  pendiente y la venta queda con ese número (y el timbrado del talonario).
- En una instalación con otra moneda (R$) el POS no lo pide, la configuración
  no ofrece el switch y no hay talonarios.
"""
import unittest
from datetime import date

from app import create_app, db
from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

CLAVE_CAJA_FLUJO_ENVIADO = 'caja_flujo_enviado_desde_vendedor'
JSON = {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}


class TestContadorPos(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Categoria, Cliente, Configuracion, MetodoPago, Producto, SesionCaja, Usuario

        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'false')
        Configuracion.establecer_bool(CLAVE_CAJA_FLUJO_ENVIADO, True)
        self.admin = Usuario.query.filter_by(username='admin').first()
        self.cliente = db.session.get(Cliente, 1)
        self.efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        db.session.add(SesionCaja(id_caja=1, id_usuario=self.admin.id_usuario, monto_inicial=0, estado='abierta'))
        categoria = Categoria(nombre='Test POS factura', activo=True)
        db.session.add(categoria)
        db.session.flush()
        self.producto = Producto(codigo='POS-FAC-1', nombre='Producto factura', id_categoria=categoria.id_categoria,
                                 precio_compra=50000, precio_venta=110000, porcentaje_iva=10, stock_actual=20,
                                 stock_minimo=1, es_servicio=False, activo=True)
        db.session.add(self.producto)
        db.session.commit()

        self.http = self.app.test_client()
        with self.http.session_transaction() as sesion:
            sesion['_user_id'] = str(self.admin.id_usuario)
            sesion['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _talonario(self):
        from app.models import TalonarioFactura

        db.session.add(TalonarioFactura(timbrado='12345678', vigencia_desde=date(2026, 1, 1),
                                        vigencia_hasta=date(2027, 12, 31), establecimiento='001',
                                        punto_expedicion='001', numero_desde=1, numero_hasta=500, activo=True))
        db.session.commit()

    def test_el_numero_viaja_con_la_venta_enviada_a_caja(self):
        from app.models import ColaCobro, Venta

        self._talonario()
        envio = self.http.post('/ventas/enviar-a-caja', headers=JSON, json={
            'id_cliente': int(self.cliente.id_cliente), 'id_usuario_vendedor': int(self.admin.id_usuario),
            'client_request_id': 'pos-factura-cola', 'numero_factura': '7',
            'items': [{'id_producto': int(self.producto.id_producto), 'cantidad': 1}],
        })
        self.assertEqual(envio.status_code, 200, envio.get_data(as_text=True))
        pendiente = ColaCobro.query.order_by(ColaCobro.id.desc()).first()
        self.assertEqual(pendiente.get_metadata()['numero_factura'], '7')

        tomar = self.http.post(f'/caja/api/cola-cobro/{pendiente.id}/tomar', headers=JSON)
        self.assertEqual(tomar.status_code, 200)
        cobro = self.http.post('/ventas/procesar', json={
            'items': [{'id_producto': int(self.producto.id_producto), 'cantidad': 1, 'precio': 110000}],
            'pagos': [{'id_metodo_pago': int(self.efectivo.id_metodo_pago), 'monto': 110000}],
            'id_cliente': int(self.cliente.id_cliente), 'id_usuario_vendedor': int(self.admin.id_usuario),
            'cola_cobro_id': int(pendiente.id), 'client_request_id': 'pos-factura-cobro',
        })
        self.assertEqual(cobro.status_code, 200, cobro.get_data(as_text=True))
        self.assertEqual(cobro.get_json()['numero_factura'], '001-001-0000007')

        venta = db.session.get(Venta, cobro.get_json()['id_venta'])
        self.assertEqual((venta.numero_factura, venta.timbrado), ('001-001-0000007', '12345678'))

    def test_numero_demasiado_largo_no_se_acepta(self):
        respuesta = self.http.post('/ventas/enviar-a-caja', headers=JSON, json={
            'id_cliente': int(self.cliente.id_cliente), 'id_usuario_vendedor': int(self.admin.id_usuario),
            'client_request_id': 'pos-factura-larga', 'numero_factura': 'x' * 81,
            'items': [{'id_producto': int(self.producto.id_producto), 'cantidad': 1}],
        })
        self.assertEqual(respuesta.status_code, 400)

    def test_en_guaranies_el_pos_y_la_configuracion_ofrecen_el_campo(self):
        pos = self.http.get('/ventas/pos').get_data(as_text=True)
        self.assertIn('const POS_MOSTRAR_NUMERO_FACTURA = true;', pos)
        self.assertIn('id="pos_numero_factura"', pos)
        config = self.http.get('/usuarios/configuracion').get_data(as_text=True)
        self.assertIn('name="mostrar_numero_factura_pos"', config)

    def test_con_otra_moneda_no_hay_numero_de_factura_en_papel(self):
        from app.models import Configuracion

        Configuracion.establecer('moneda_simbolo', 'R$')
        Configuracion.establecer('moneda_locale', 'pt-BR')
        db.session.commit()

        pos = self.http.get('/ventas/pos').get_data(as_text=True)
        self.assertIn('const POS_MOSTRAR_NUMERO_FACTURA = false;', pos)
        config = self.http.get('/usuarios/configuracion').get_data(as_text=True)
        self.assertNotIn('name="mostrar_numero_factura_pos"', config)
        self.assertEqual(self.http.get('/contador/talonarios').status_code, 302)


if __name__ == '__main__':
    unittest.main()
