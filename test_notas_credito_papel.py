"""Notas de crédito en papel: el comprobante de una devolución resta del débito.

Sin facturación electrónica, una devolución de una venta con factura lleva su
nota de crédito en papel. Se carga desde la venta; su IVA sale de las líneas
devueltas (cada una con su porcentaje) y resta del débito del mes de la NC.
Una devolución sin NC es un pendiente. La devolución en sí no cambia.

Portado de sistema_silvio_cel (fase 2: sólo el lado que lee el resumen). El
formulario para cargar la NC desde la venta llega en la fase 4: acá se carga
con el servicio. La devolución reembolsa lo cobrado con el descuento global,
como la factura; con una moneda con centavos (R$), redondeado a centavos.
"""
import unittest
from datetime import date, datetime

from app import create_app, db
from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

MES = '2026-09'
PRIMERO = date(2026, 9, 1)
EN_EL_MES = datetime(2026, 9, 15, 15, 0)   # mediodía en Asunción: lejos de los bordes UTC


class TestNotasCreditoPapel(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Categoria, Cliente, Configuracion, Producto, SesionCaja, Usuario

        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'false')
        Configuracion.establecer('devoluciones_activo', 'true')
        self.admin = Usuario.query.filter_by(username='admin').first()
        self.cliente = db.session.get(Cliente, 1)
        self.sesion = SesionCaja(id_caja=1, id_usuario=self.admin.id_usuario, monto_inicial=0, estado='abierta')
        categoria = Categoria(nombre='NC papel', activo=True)
        db.session.add_all([self.sesion, categoria])
        db.session.flush()
        self.producto = Producto(codigo='NC-1', nombre='Cargador', id_categoria=categoria.id_categoria,
                                 precio_compra=1000, precio_venta=110000, porcentaje_iva=10,
                                 stock_actual=10, stock_minimo=1, es_servicio=False, activo=True)
        db.session.add(self.producto)
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as sesion:
            sesion['_user_id'] = str(self.admin.id_usuario)
            sesion['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _venta(self, numero='001-001-0000050', lineas=((110000, 10),)):
        """Venta con una línea por (subtotal, % IVA)."""
        from app.models import DetalleVenta, Venta

        total = sum(s for s, _ in lineas)
        iva10 = sum(s / 11 for s, p in lineas if p == 10)
        iva5 = sum(s / 21 for s, p in lineas if p == 5)
        venta = Venta(id_cliente=self.cliente.id_cliente, id_sesion_caja=self.sesion.id_sesion,
                      subtotal=total, total=total, total_iva_10=iva10, total_iva_5=iva5, total_exenta=0,
                      numero_factura=numero, estado='completada', fecha_venta=EN_EL_MES)
        db.session.add(venta)
        db.session.flush()
        for subtotal, porcentaje in lineas:
            db.session.add(DetalleVenta(id_venta=venta.id_venta, id_producto=self.producto.id_producto,
                                        cantidad=1, precio_unitario=subtotal, precio_original=subtotal,
                                        porcentaje_iva=porcentaje, monto_iva=0, subtotal=subtotal))
        db.session.commit()
        return venta

    def _devolucion(self, venta, montos=None, estado='completada'):
        from app.models import DetalleDevolucion, Devolucion

        detalles = venta.detalles.all()
        montos = montos or [float(d.subtotal) for d in detalles]
        devolucion = Devolucion(id_venta=venta.id_venta, id_usuario=self.admin.id_usuario,
                                id_sesion_caja=self.sesion.id_sesion, fecha_devolucion=EN_EL_MES,
                                motivo='Falla', accion_stock='retorno_stock', monto_total=sum(montos),
                                estado=estado)
        db.session.add(devolucion)
        db.session.flush()
        for detalle, monto in zip(detalles, montos):
            db.session.add(DetalleDevolucion(id_devolucion=devolucion.id_devolucion, id_producto=detalle.id_producto,
                                             id_detalle_venta_original=detalle.id_detalle_venta,
                                             cantidad=1, precio_unitario=monto, subtotal=monto))
        db.session.commit()
        return devolucion

    def _nc(self, devolucion, numero='001-001-0000045', fecha='2026-09-20'):
        from app.services.notas_credito_papel import registrar

        nota, error = registrar(devolucion, numero, '87654321', date.fromisoformat(fecha), self.admin.id_usuario)
        db.session.commit()
        return nota, error

    def test_iva_de_la_devolucion_sale_de_cada_linea(self):
        from app.services.notas_credito_papel import totales_de_devolucion

        venta = self._venta(lineas=((110000, 10), (21000, 5), (5000, 0)))
        t = totales_de_devolucion(self._devolucion(venta))

        self.assertAlmostEqual(t['iva10'], 10000)
        self.assertAlmostEqual(t['base10'], 100000)
        self.assertAlmostEqual(t['iva5'], 1000)
        self.assertAlmostEqual(t['base5'], 20000)
        self.assertAlmostEqual(t['exenta'], 5000)
        self.assertAlmostEqual(t['total'], 136000)

    def test_devolucion_sin_nc_es_pendiente_y_con_nc_resta_del_debito(self):
        from app.models import NotaCreditoPapel
        from app.services.resumen_contadora import resumen_del_mes

        venta = self._venta()
        devolucion = self._devolucion(venta, montos=[55000])     # devolución parcial

        r = resumen_del_mes(PRIMERO, fe_activa=False)
        self.assertAlmostEqual(r['debito'], 10000)
        self.assertEqual(r['en_papel']['sin_nota_credito']['cantidad'], 1)
        self.assertEqual(r['pendientes'], 1)
        _, error = self._nc(devolucion, numero='001-001-45')
        self.assertIsNone(error)
        nota = NotaCreditoPapel.query.one()
        self.assertEqual((nota.numero, nota.timbrado, nota.fecha), ('001-001-0000045', '87654321', date(2026, 9, 20)))

        r = resumen_del_mes(PRIMERO, fe_activa=False)
        self.assertAlmostEqual(r['en_papel']['notas_credito']['iva10'], 5000)
        self.assertAlmostEqual(r['debito'], 5000)
        self.assertEqual(r['pendientes'], 0)

        pantalla = self.client.get(f'/contador/iva?mes={MES}').get_data(as_text=True)
        self.assertIn("abrir('notas_papel')", pantalla)
        detalle = self.client.get(f'/contador/iva/detalle?mes={MES}&fila=notas_papel').get_data(as_text=True)
        self.assertIn('001-001-0000045', detalle)
        self.assertIn('001-001-0000050', detalle)            # la factura que afecta
        self.assertIn('87654321', detalle)

    def test_nc_cuenta_en_el_mes_de_su_fecha(self):
        from app.services.resumen_contadora import resumen_del_mes

        devolucion = self._devolucion(self._venta())
        self._nc(devolucion, fecha='2026-10-02')

        septiembre = resumen_del_mes(PRIMERO, fe_activa=False)['en_papel']
        octubre = resumen_del_mes(date(2026, 10, 1), fe_activa=False)['en_papel']
        self.assertEqual(septiembre['notas_credito']['cantidad'], 0)
        self.assertEqual(septiembre['sin_nota_credito']['cantidad'], 0)   # ya tiene NC
        self.assertEqual(octubre['notas_credito']['cantidad'], 1)

    def test_validaciones_y_quitar(self):
        from app.models import NotaCreditoPapel
        from app.services.notas_credito_papel import registrar

        sin_factura = self._devolucion(self._venta(numero=None))
        _, error = registrar(sin_factura, '1', '', date(2026, 9, 20))
        self.assertIn('no tiene número de factura', error)

        anulada = self._devolucion(self._venta(numero='001-001-0000060'), estado='anulada')
        _, error = registrar(anulada, '1', '', date(2026, 9, 20))
        self.assertIn('anulada', error)

        primera = self._devolucion(self._venta(numero='001-001-0000070'))
        segunda = self._devolucion(self._venta(numero='001-001-0000071'))
        self._nc(primera)
        _, error = self._nc(segunda)
        self.assertEqual(NotaCreditoPapel.query.count(), 1)
        self.assertIn('ya está cargada', error)

        self._nc(primera, numero='')
        self.assertEqual(NotaCreditoPapel.query.count(), 0)

    def test_con_facturacion_electronica_no_se_carga(self):
        from app.models import Configuracion
        from app.services.notas_credito_papel import registrar

        devolucion = self._devolucion(self._venta())
        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'true')
        db.session.commit()

        _, error = registrar(devolucion, '1', '', date(2026, 9, 20))

        self.assertIn('SIFEN', error)

    def test_anular_venta_excluye_nc_y_pendientes(self):
        from app.services.resumen_contadora import resumen_del_mes
        from app.services.notas_credito_papel import registrar

        venta = self._venta()
        devolucion = self._devolucion(venta, montos=[55000])
        self._nc(devolucion)
        # El endpoint real permite anular una venta con devoluciones previas.
        respuesta = self.client.post(f'/ventas/{venta.id_venta}/anular')
        self.assertEqual(respuesta.status_code, 302)
        db.session.refresh(venta)
        self.assertEqual(venta.estado, 'anulada')
        r = resumen_del_mes(PRIMERO, False)
        self.assertEqual(r['debito'], 0)
        self.assertEqual(r['en_papel']['notas_credito']['cantidad'], 0)
        _, error = registrar(devolucion, '002', '', date(2026, 9, 20))
        self.assertIn('venta está anulada', error)

        db.session.delete(devolucion.nota_credito_papel)
        db.session.commit()
        self.assertEqual(resumen_del_mes(PRIMERO, False)['en_papel']['sin_nota_credito']['cantidad'], 0)

    def test_devolucion_descontada_cierra_caja_factura_y_nota(self):
        from app.models import Devolucion, MovimientoCaja
        from app.services.devoluciones import lineas_devolubles
        from app.services.resumen_contadora import resumen_del_mes

        venta = self._venta()
        venta.total = 99000
        venta.descuento_monto = 11000
        db.session.commit()
        self.assertEqual(lineas_devolubles(venta)[0]['precio_unitario'], 99000)
        respuesta = self._devolver(venta, 1)
        self.assertEqual(respuesta.get_json()['monto_total'], 99000)
        devolucion = db.session.get(Devolucion, respuesta.get_json()['id_devolucion'])
        movimiento = MovimientoCaja.query.filter_by(
            referencia_tipo='devolucion', referencia_id=devolucion.id_devolucion).one()
        self.assertEqual(float(movimiento.monto), 99000)
        self._nc(devolucion)
        r = resumen_del_mes(PRIMERO, False)
        self.assertEqual(r['en_papel']['notas_credito']['iva10'], 9000)
        self.assertEqual(r['debito'], 0)

    def _devolver(self, venta, cantidad):
        respuesta = self.client.post(f'/ventas/{venta.id_venta}/devolucion', json={
            'items': [{'id_detalle_venta': venta.detalles.first().id_detalle_venta, 'cantidad': cantidad}],
            'motivo': 'Falla', 'accion_stock': 'retorno_stock', 'metodo_reembolso': 'efectivo'})
        self.assertEqual(respuesta.status_code, 200, respuesta.get_data(as_text=True))
        return respuesta

    def test_con_centavos_el_descuento_se_reparte_sin_redondear_a_enteros(self):
        """Instalación en R$: el reembolso va a centavos y en partes suma lo cobrado."""
        from app.models import Configuracion, DetalleVenta, Venta

        Configuracion.establecer('moneda_simbolo', 'R$')
        Configuracion.establecer('moneda_decimales', '2')
        venta = Venta(id_cliente=self.cliente.id_cliente, id_sesion_caja=self.sesion.id_sesion,
                      subtotal=100, total=95, descuento_monto=5, estado='completada', fecha_venta=EN_EL_MES)
        db.session.add(venta)
        db.session.flush()
        db.session.add(DetalleVenta(id_venta=venta.id_venta, id_producto=self.producto.id_producto, cantidad=3,
                                    precio_unitario=100 / 3, precio_original=100 / 3, porcentaje_iva=10,
                                    monto_iva=0, subtotal=100))
        db.session.commit()

        primera = self._devolver(venta, 1).get_json()['monto_total']
        resto = self._devolver(venta, 2).get_json()['monto_total']

        self.assertAlmostEqual(primera, 31.67)
        self.assertAlmostEqual(resto, 63.33)
        self.assertAlmostEqual(primera + resto, 95.00)

    def test_devolucion_antigua_excesiva_avisa_sin_reescribir_importes(self):
        from app.services.resumen_contadora import resumen_del_mes

        venta = self._venta()
        venta.total = 99000
        db.session.commit()
        devolucion = self._devolucion(venta)  # devuelve 110.000, sin el descuento
        self._nc(devolucion)
        avisos = resumen_del_mes(PRIMERO, False)['controles']['conciliacion']['filas']
        self.assertTrue(any('importe devuelto supera' in aviso for aviso in avisos))
        self.assertEqual(float(devolucion.monto_total), 110000)
        html = self.client.get(f'/contador/iva?mes={MES}').get_data(as_text=True)
        self.assertIn('importe devuelto supera', html)


if __name__ == '__main__':
    unittest.main()
