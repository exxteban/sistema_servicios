"""Talonario de facturas en papel: número siguiente, timbrado y revisión del mes.

Sin facturación electrónica el POS ofrece el número que sigue, completa lo
que se tipea ("124" → "001-001-0000124") y cada venta guarda su timbrado.
El resumen para el/la contador/a marca los números que no caen en ningún
talonario y avisa de los saltos. Nunca se bloquea una venta.
"""
import unittest
from datetime import date, datetime

from app import create_app, db
from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

MES = '2026-09'
EN_EL_MES = datetime(2026, 9, 15, 15, 0)   # mediodía en Asunción: lejos de los bordes UTC


class TestTalonarioFacturas(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, Configuracion, MetodoPago, SesionCaja, Usuario

        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'false')
        self.admin = Usuario.query.filter_by(username='admin').first()
        self.cliente = db.session.get(Cliente, 1)
        self.efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        self.sesion = SesionCaja(id_caja=1, id_usuario=self.admin.id_usuario, monto_inicial=0, estado='abierta')
        db.session.add(self.sesion)
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as sesion:
            sesion['_user_id'] = str(self.admin.id_usuario)
            sesion['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _talonario(self, desde=1, hasta=500, punto='001', vence=date(2027, 6, 30), activo=True):
        from app.models import TalonarioFactura

        talonario = TalonarioFactura(
            timbrado='12345678', vigencia_desde=date(2026, 1, 1), vigencia_hasta=vence,
            establecimiento='001', punto_expedicion=punto, numero_desde=desde, numero_hasta=hasta,
            activo=activo,
        )
        db.session.add(talonario)
        db.session.commit()
        return talonario

    def _venta(self, numero, estado='completada', fecha=EN_EL_MES, timbrado=None):
        from app.models import Venta

        venta = Venta(
            id_cliente=self.cliente.id_cliente, id_sesion_caja=self.sesion.id_sesion,
            subtotal=110000, total=110000, total_iva_10=10000, total_iva_5=0, total_exenta=0,
            numero_factura=numero, estado=estado, fecha_venta=fecha, timbrado=timbrado,
        )
        db.session.add(venta)
        db.session.commit()
        return venta

    # --- Servicio ------------------------------------------------------------

    def test_crear_talonario_valida_los_datos(self):
        from app.services.talonario_facturas import crear_talonario

        ok, error = crear_talonario('12345678', date(2026, 1, 1), date(2026, 12, 31), '1', '2', 1, 500)
        self.assertIsNone(error)
        self.assertEqual((ok.establecimiento, ok.punto_expedicion), ('001', '002'))

        _, error = crear_talonario('1234', date(2026, 1, 1), date(2026, 12, 31), '001', '001', 1, 500)
        self.assertIn('8 números', error)
        _, error = crear_talonario('12345678', date(2026, 12, 31), date(2026, 1, 1), '001', '001', 1, 500)
        self.assertIn('vigencia', error)
        _, error = crear_talonario('12345678', date(2026, 1, 1), date(2026, 12, 31), '001', '001', 500, 1)
        self.assertIn('rango', error)

        self._talonario()
        _, error = crear_talonario('87654321', date(2026, 6, 1), date(2027, 6, 1), '001', '001', 400, 900)
        self.assertIn('Se superpone', error)

    def test_normaliza_lo_que_se_tipea(self):
        from app.services.talonario_facturas import normalizar_numero

        hoy = date(2026, 9, 15)
        self.assertEqual(normalizar_numero('001-001-5', hoy), '001-001-0000005')
        self.assertEqual(normalizar_numero('124', hoy), '124')            # sin talonario no se adivina
        self._talonario()
        self.assertEqual(normalizar_numero(' 124 ', hoy), '001-001-0000124')
        self._talonario(punto='002')
        self.assertEqual(normalizar_numero('124', hoy), '124')            # dos talonarios: ambiguo

    def test_siguiente_cuenta_tambien_las_anuladas_y_avisa_si_se_termina(self):
        from app.services.talonario_facturas import siguiente

        talonario = self._talonario(desde=1, hasta=7)
        self.assertEqual(siguiente(talonario), 1)
        self._venta('001-001-0000005')
        self._venta('001-001-0000006', estado='anulada')
        self._venta('001-002-0000009')                                    # otro punto: no cuenta
        self.assertEqual(siguiente(talonario), 7)
        self._venta('001-001-0000007')
        self.assertIsNone(siguiente(talonario))

    # --- POS -----------------------------------------------------------------

    def test_pos_ofrece_el_siguiente_y_la_venta_guarda_numero_completo_y_timbrado(self):
        from app.models import Categoria, Producto, Venta

        self._talonario(desde=120, hasta=500)
        sugerencia = self.client.get('/contador/talonarios/siguiente').get_json()['sugerencias'][0]
        self.assertEqual(sugerencia['numero'], '001-001-0000120')
        self.assertEqual(sugerencia['timbrado'], '12345678')

        categoria = Categoria(nombre='Talonario', activo=True)
        db.session.add(categoria)
        db.session.flush()
        producto = Producto(codigo='TAL-1', nombre='Funda', id_categoria=categoria.id_categoria,
                            precio_compra=1000, precio_venta=11000, porcentaje_iva=10,
                            stock_actual=10, stock_minimo=1, es_servicio=False, activo=True)
        db.session.add(producto)
        db.session.commit()

        respuesta = self.client.post('/ventas/procesar', json={
            'items': [{'id_producto': producto.id_producto, 'cantidad': 1}],
            'pagos': [{'id_metodo_pago': self.efectivo.id_metodo_pago, 'monto': 11000}],
            'id_cliente': self.cliente.id_cliente, 'id_usuario_vendedor': self.admin.id_usuario,
            'client_request_id': 'talonario-120', 'numero_factura': '120',
        })

        self.assertEqual(respuesta.status_code, 200, respuesta.get_data(as_text=True))
        self.assertEqual(respuesta.get_json()['numero_factura'], '001-001-0000120')
        venta = Venta.query.filter_by(client_request_id='talonario-120').one()
        self.assertEqual((venta.numero_factura, venta.timbrado), ('001-001-0000120', '12345678'))
        siguiente = self.client.get('/contador/talonarios/siguiente').get_json()['sugerencias'][0]
        self.assertEqual(siguiente['numero'], '001-001-0000121')

    def test_con_facturacion_electronica_no_hay_sugerencias_ni_correccion(self):
        from app.models import Configuracion

        self._talonario()
        venta = self._venta('001-001-0000001')
        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'true')
        db.session.commit()
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion['_user_id'] = str(self.admin.id_usuario)
            sesion['_fresh'] = True

        self.assertEqual(cliente.get('/contador/talonarios/siguiente').get_json(), {'sugerencias': []})
        respuesta = cliente.post(f'/contador/venta/{venta.id_venta}/numero-factura', data={'numero_factura': '2'})
        self.assertEqual(respuesta.status_code, 404)

    # --- Pantallas -----------------------------------------------------------

    def test_pantalla_de_talonarios_crea_y_desactiva(self):
        from app.models import TalonarioFactura

        respuesta = self.client.post('/contador/talonarios', data={
            'timbrado': '12345678', 'vigencia_desde': '2026-01-01', 'vigencia_hasta': '2026-12-31',
            'establecimiento': '1', 'punto_expedicion': '1', 'numero_desde': '1', 'numero_hasta': '500',
        })
        self.assertEqual(respuesta.status_code, 302)
        talonario = TalonarioFactura.query.one()
        html = self.client.get('/contador/talonarios').get_data(as_text=True)
        self.assertIn('001-001-0000001 al 0000500', html)

        error = self.client.post('/contador/talonarios', data={
            'timbrado': '99', 'vigencia_desde': '2026-01-01', 'vigencia_hasta': '2026-12-31',
            'establecimiento': '1', 'punto_expedicion': '1', 'numero_desde': '1', 'numero_hasta': '5',
        }).get_data(as_text=True)
        self.assertIn('8 números', error)
        self.assertEqual(TalonarioFactura.query.count(), 1)

        self.client.post(f'/contador/talonarios/{talonario.id}/activo')
        self.assertFalse(db.session.get(TalonarioFactura, talonario.id).activo)

    def test_corregir_numero_desde_la_venta_asigna_timbrado_y_audita(self):
        from app.models import Auditoria

        self._talonario()
        venta = self._venta(None)

        html = self.client.get(f'/ventas/{venta.id_venta}').get_data(as_text=True)
        self.assertIn('Cargar número', html)

        self.client.post(f'/contador/venta/{venta.id_venta}/numero-factura', data={'numero_factura': '33'})
        db.session.refresh(venta)
        self.assertEqual((venta.numero_factura, venta.timbrado), ('001-001-0000033', '12345678'))
        self.assertIsNotNone(Auditoria.query.filter_by(accion='corregir_numero_factura').first())

        self.client.post(f'/contador/venta/{venta.id_venta}/numero-factura', data={'numero_factura': ''})
        db.session.refresh(venta)
        self.assertEqual((venta.numero_factura, venta.timbrado), (None, None))

    # --- Resumen para el/la contador/a ---------------------------------------

    def test_resumen_marca_fuera_de_talonario_y_saltos(self):
        from app.services.resumen_contadora import resumen_del_mes

        self._venta('001-001-0000010')                       # anterior al talonario: se resuelve igual
        self._venta('001-001-0000013', estado='anulada')     # consume número: no es salto
        self._venta('001-001-0000014', timbrado='12345678')
        self._venta('001-001-0999999')                       # fuera del rango
        self._talonario(desde=1, hasta=500)

        r = resumen_del_mes(date(2026, 9, 1), fe_activa=False)
        revision = r['en_papel']['talonario']

        self.assertEqual([f['numero'] for f in revision['fuera_de_talonario']], ['001-001-0999999'])
        self.assertEqual(r['pendientes'], 1)
        self.assertEqual(revision['saltos']['numeros'][:2], ['001-001-0000011', '001-001-0000012'])

        html = self.client.get(f'/contador/iva?mes={MES}').get_data(as_text=True)
        self.assertIn('no corresponde a ningún talonario', html)
        self.assertIn('Saltos en la numeración', html)
        detalle = self.client.get(f'/contador/iva/detalle?mes={MES}&fila=ventas_factura').get_data(as_text=True)
        self.assertIn('Timbrado', detalle)
        self.assertEqual(detalle.count('12345678'), 2)

    def test_numero_mal_tipeado_no_inventa_saltos(self):
        from app.services.resumen_contadora import resumen_del_mes

        self._talonario(desde=1, hasta=500)
        self._venta('001-001-0000010')
        self._venta('001-001-0000012')
        self._venta('001-001-0999999')                       # typo: fuera del rango, ya es pendiente

        saltos = resumen_del_mes(date(2026, 9, 1), fe_activa=False)['en_papel']['talonario']['saltos']

        self.assertEqual(saltos, {'cantidad': 1, 'numeros': ['001-001-0000011']})

    def test_informe_dice_cuantos_saltos_no_se_listan(self):
        from app.services.resumen_contadora_informe import informe_del_mes

        self._talonario(desde=1, hasta=500)
        self._venta('001-001-0000001')
        self._venta('001-001-0000015')                       # 13 números en el medio

        informe = informe_del_mes(date(2026, 9, 1), fe_activa=False)

        aviso = next(a for a in informe['avisos'] if a.startswith('Saltos'))
        self.assertIn('13 número(s) sin venta', aviso)
        self.assertIn('y 3 más', aviso)

    def test_cambio_de_timbrado_no_es_un_salto(self):
        from app.models import TalonarioFactura
        from app.services.resumen_contadora import resumen_del_mes

        self._talonario(desde=1, hasta=100, vence=date(2026, 9, 10))
        db.session.add(TalonarioFactura(
            timbrado='87654321', vigencia_desde=date(2026, 9, 11), vigencia_hasta=date(2027, 9, 30),
            establecimiento='001', punto_expedicion='001', numero_desde=1, numero_hasta=100, activo=True))
        db.session.commit()
        self._venta('001-001-0000099', fecha=datetime(2026, 9, 5, 15, 0))
        self._venta('001-001-0000100', fecha=datetime(2026, 9, 8, 15, 0))
        self._venta('001-001-0000001', fecha=datetime(2026, 9, 15, 15, 0))
        self._venta('001-001-0000002', fecha=datetime(2026, 9, 16, 15, 0))

        saltos = resumen_del_mes(date(2026, 9, 1), fe_activa=False)['en_papel']['talonario']['saltos']

        self.assertEqual(saltos['cantidad'], 0)

    def test_sin_talonario_invita_a_cargarlo(self):
        self._venta('001-001-0000010')

        html = self.client.get(f'/contador/iva?mes={MES}').get_data(as_text=True)

        self.assertIn('talonario de facturas', html)
        self.assertIn('/contador/talonarios', html)


    def _timbrado_siguiente(self):
        from app.models import TalonarioFactura

        self._talonario(desde=1, hasta=100, vence=date(2026, 9, 10))
        nuevo = TalonarioFactura(
            timbrado='87654321', vigencia_desde=date(2026, 9, 11), vigencia_hasta=date(2027, 9, 30),
            establecimiento='001', punto_expedicion='001', numero_desde=1, numero_hasta=100, activo=True)
        db.session.add(nuevo)
        db.session.commit()
        return nuevo

    def test_timbrado_nuevo_empieza_de_cero_aunque_el_anterior_se_haya_terminado(self):
        from app.services.talonario_facturas import siguiente

        nuevo = self._timbrado_siguiente()
        self._venta('001-001-0000100', fecha=datetime(2026, 9, 8, 15, 0), timbrado='12345678')
        self._venta('001-001-0000099', fecha=datetime(2026, 9, 7, 15, 0))   # histórica sin timbrado

        self.assertEqual(siguiente(nuevo), 1)
        self._venta('001-001-0000001', fecha=datetime(2026, 9, 15, 15, 0), timbrado='87654321')
        self.assertEqual(siguiente(nuevo), 2)

    def test_mismo_numero_con_otro_timbrado_no_es_repetido(self):
        from app.services.resumen_contadora import resumen_del_mes

        self._timbrado_siguiente()
        self._venta('001-001-0000001', fecha=datetime(2026, 9, 8, 15, 0), timbrado='12345678')
        self._venta('001-001-0000001', fecha=datetime(2026, 9, 15, 15, 0), timbrado='87654321')
        self.assertEqual(resumen_del_mes(date(2026, 9, 1), False)['en_papel']['repetidos'], [])

        otra = self._venta('001-001-0000001', fecha=datetime(2026, 9, 16, 15, 0), timbrado='87654321')
        repetidos = resumen_del_mes(date(2026, 9, 1), False)['en_papel']['repetidos']
        self.assertEqual(len(repetidos), 1)
        self.assertIn(otra.id_venta, repetidos[0]['ventas'])
        self.assertEqual(len(repetidos[0]['ventas']), 2)


if __name__ == '__main__':
    unittest.main()
