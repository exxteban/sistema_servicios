"""Área Contador/a sin facturación electrónica: el débito sale de las ventas en papel.

La mayoría de las instalaciones factura con talonario o autoimpresor y carga
el número en el campo "Nº Factura" del POS. Esas ventas son el débito fiscal;
las que no tienen número no suman, y un número repetido es un pendiente.

Portado de sistema_silvio_cel. En este sistema el POS todavía no tiene el
campo (fase 4): los tests cargan `Venta.numero_factura` directo.
"""
import unittest
from datetime import date, datetime

from app import db
from app.models import Configuracion, Venta
from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

from test_facturacion_electronica_proveedor_base import BaseProveedorApi

MES = '2026-09'
PRIMERO = date(2026, 9, 1)
EN_EL_MES = datetime(2026, 9, 15, 15, 0)   # mediodía en Asunción: lejos de los bordes UTC


class TestContadorVentasPapel(BaseProveedorApi):
    def setUp(self):
        super().setUp()
        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'false')
        db.session.commit()

    def _get(self, url):
        from app.models import Usuario

        usuario = Usuario.query.filter_by(username='admin').first()
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion['_user_id'] = str(usuario.id_usuario)
            sesion['_fresh'] = True
        return cliente.get(url)

    def _venta_papel(self, numero, iva10, subtotal=110000, total=None, estado='completada',
                     fecha=EN_EL_MES):
        venta = Venta(
            id_cliente=self.cliente.id_cliente, id_sesion_caja=self.sesion.id_sesion,
            subtotal=subtotal, total=subtotal if total is None else total,
            total_iva_10=iva10, total_iva_5=0, total_exenta=0,
            numero_factura=numero, estado=estado, fecha_venta=fecha,
        )
        db.session.add(venta)
        db.session.commit()
        return venta

    def test_debito_sale_de_las_ventas_con_numero(self):
        from app.services.resumen_contadora import resumen_del_mes

        self._venta_papel('001-001-0000101', 10000)
        # Con descuento: la factura dice lo cobrado, el IVA se escala igual.
        self._venta_papel('001-001-0000102', 10000, subtotal=110000, total=99000)
        self._venta_papel(None, 10000)                       # ticket: no suma
        self._venta_papel('   ', 10000)                      # número en blanco: tampoco
        self._venta_papel('001-001-0000103', 10000, estado='anulada')
        self._venta_papel('001-001-0000104', 10000, fecha=datetime(2026, 10, 2, 15, 0))

        r = resumen_del_mes(PRIMERO, fe_activa=False)

        self.assertIsNone(r['documentos'])
        papel = r['en_papel']
        self.assertEqual(papel['ventas']['cantidad'], 2)
        self.assertAlmostEqual(papel['ventas']['iva10'], 10000 + 9000)
        self.assertAlmostEqual(papel['ventas']['base10'], 190000)
        self.assertAlmostEqual(papel['ventas']['total'], 110000 + 99000)
        self.assertAlmostEqual(r['debito'], 19000)
        self.assertEqual(papel['sin_numero'], {'cantidad': 2, 'total': 220000.0})
        self.assertEqual(papel['anuladas']['cantidad'], 1)
        self.assertEqual(papel['anuladas']['filas'][0]['numero'], '001-001-0000103')
        self.assertEqual(papel['repetidos'], [])
        self.assertEqual(r['pendientes'], 0)

    def test_numero_repetido_es_pendiente(self):
        from app.services.resumen_contadora import resumen_del_mes

        a = self._venta_papel('001-001-0000200', 10000)
        b = self._venta_papel('001-001-0000200', 5000)

        r = resumen_del_mes(PRIMERO, fe_activa=False)

        self.assertEqual(r['en_papel']['repetidos'],
                         [{'numero': '001-001-0000200', 'ventas': [a.id_venta, b.id_venta]}])
        self.assertEqual(r['pendientes'], 1)
        html = self._get(f'/contador/iva?mes={MES}').get_data(as_text=True)
        self.assertIn('El número de factura 001-001-0000200 está cargado en 2 ventas', html)

    def test_con_facturacion_electronica_no_mira_las_ventas_en_papel(self):
        from app.services.resumen_contadora import resumen_del_mes

        self._venta_papel('001-001-0000300', 10000)

        r = resumen_del_mes(PRIMERO, fe_activa=True, ambiente='prod')

        self.assertIsNone(r['en_papel'])
        self.assertEqual(r['debito'], 0)

    def test_pantalla_y_detalle_de_ventas_en_papel(self):
        self._venta_papel('001-001-0000401', 10000)
        self._venta_papel('001-001-0000402', 10000, estado='anulada')

        html = self._get(f'/contador/iva?mes={MES}').get_data(as_text=True)
        self.assertIn('Ventas con número de factura', html)
        self.assertIn('₲ 10.000', html)
        self.assertIn('001-001-0000402', html)                  # pestaña de anuladas
        self.assertIn("abrir('ventas_factura')", html)

        detalle = self._get(f'/contador/iva/detalle?mes={MES}&fila=ventas_factura').get_data(as_text=True)
        self.assertIn('001-001-0000401', detalle)
        self.assertNotIn('001-001-0000402', detalle)
        excel = self._get(f'/contador/iva/detalle?mes={MES}&fila=ventas_factura&formato=xlsx')
        self.assertEqual(excel.status_code, 200)
        # Las filas de SIFEN no existen sin facturación electrónica.
        self.assertEqual(self._get(f'/contador/iva/detalle?mes={MES}&fila=ventas').status_code, 404)

    def test_con_facturacion_electronica_no_hay_detalle_en_papel(self):
        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'true')
        db.session.commit()

        respuesta = self._get(f'/contador/iva/detalle?mes={MES}&fila=ventas_factura')

        self.assertEqual(respuesta.status_code, 404)

    def test_avisa_que_las_ventas_todavia_no_guardan_la_factura(self):
        """En este sistema el POS no carga el número todavía (fase 4): se avisa."""
        html = self._get(f'/contador/iva?mes={MES}').get_data(as_text=True)

        self.assertIn('todavía no guardan el número de la factura en papel', html)
        self.assertNotIn('El POS no está pidiendo el número de factura', html)

    def test_menu_lateral_tiene_el_apartado_contador(self):
        html = self._get(f'/contador/iva?mes={MES}').get_data(as_text=True)

        self.assertIn('data-sidebar-trigger="contador"', html)
        self.assertIn('Resumen de IVA del mes', html)


if __name__ == '__main__':
    unittest.main()
