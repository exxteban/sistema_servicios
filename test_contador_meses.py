"""Saldo del mes con lo que se carga a mano, y el mes presentado.

saldo = débito − crédito − saldo a favor anterior − retenciones. Al marcar un
mes presentado se guarda una foto del débito y el crédito: si después cambian
se avisa (no se bloquea nada), y su saldo a favor se sugiere en el siguiente.
"""
from datetime import date, datetime

from app import db
from app.models import Auditoria, Configuracion, ContadorMes, Usuario, Venta
from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

from test_facturacion_electronica_proveedor_base import BaseProveedorApi


class TestContadorMeses(BaseProveedorApi):
    def setUp(self):
        super().setUp()
        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'false')
        db.session.commit()
        self.http = self.app.test_client()
        with self.http.session_transaction() as sesion:
            sesion['_user_id'] = str(Usuario.query.filter_by(username='admin').first().id_usuario)
            sesion['_fresh'] = True

    def _venta(self, numero, iva10, fecha=datetime(2026, 9, 15, 15)):
        db.session.add(Venta(id_cliente=self.cliente.id_cliente, id_sesion_caja=self.sesion.id_sesion,
                             subtotal=iva10 * 11, total=iva10 * 11, total_iva_10=iva10, numero_factura=numero,
                             fecha_venta=fecha))
        db.session.commit()

    def test_saldo_con_saldo_anterior_y_retenciones(self):
        self._venta('001-001-0000001', 50000)

        self.http.post('/contador/iva/ajustes', data={'mes': '2026-09', 'saldo_favor_anterior': '20.000',
                                                      'retenciones': '5.000'})

        html = self.http.get('/contador/iva?mes=2026-09').get_data(as_text=True)
        self.assertIn('₲ 25.000', html)                      # 50.000 − 0 − 20.000 − 5.000
        self.assertIn('saldo a favor anterior (₲ 20.000)', html)
        r = ContadorMes.query.filter_by(periodo='2026-09').one()
        self.assertEqual((float(r.saldo_favor_anterior), float(r.retenciones)), (20000, 5000))

        error = self.http.post('/contador/iva/ajustes', data={'mes': '2026-09', 'saldo_favor_anterior': '-3',
                                                              'retenciones': ''}, follow_redirects=True)
        self.assertIn('sin signo', error.get_data(as_text=True))

    def test_presentado_avisa_si_cambia_y_sugiere_el_saldo_al_mes_siguiente(self):
        from app.services.contador_meses import saldo_favor_sugerido

        self._venta('001-001-0000001', 10000)
        self.http.post('/contador/iva/ajustes', data={'mes': '2026-09', 'saldo_favor_anterior': '30.000',
                                                      'retenciones': '0'})
        self.http.post('/contador/iva/presentado', data={'mes': '2026-09', 'presentado': '1'})

        r = ContadorMes.query.filter_by(periodo='2026-09').one()
        self.assertTrue(r.presentado)
        self.assertEqual(float(r.debito_presentado), 10000)
        self.assertIsNotNone(Auditoria.query.filter_by(accion='contador_mes_presentado').first())
        html = self.http.get('/contador/iva?mes=2026-09').get_data(as_text=True)
        self.assertIn('Presentado el', html)
        self.assertNotIn('Cambió después de presentado', html)

        # Septiembre cerró con 20.000 a favor: octubre lo sugiere.
        self.assertEqual(saldo_favor_sugerido(date(2026, 10, 1)), 20000)
        octubre = self.http.get('/contador/iva?mes=2026-10').get_data(as_text=True)
        self.assertIn('value="20.000"', octubre)

        # Alguien carga una factura de septiembre después de presentado.
        self._venta('001-001-0000002', 4000)
        self.http.post('/contador/iva/presentado', data={'mes': '2026-09', 'presentado': '1'})
        html = self.http.get('/contador/iva?mes=2026-09').get_data(as_text=True)
        self.assertIn('Cambió después de presentado: débito ₲ 10.000 → ₲ 14.000', html)

        self.http.post('/contador/iva/presentado', data={'mes': '2026-09', 'presentado': '0'})
        db.session.refresh(r)
        self.assertFalse(r.presentado)
        self.assertIsNone(r.debito_presentado)
        self.assertIsNone(saldo_favor_sugerido(date(2026, 10, 1)))

    def test_cargar_cero_descarta_la_sugerencia(self):
        """Guardar 0 de saldo anterior pisa lo sugerido, en la pantalla y en lo presentado."""
        from app.services.contador_meses import estado_del_mes

        self._venta('001-001-0000001', 10000)
        self.http.post('/contador/iva/ajustes', data={'mes': '2026-09', 'saldo_favor_anterior': '30.000',
                                                      'retenciones': '0'})
        self.http.post('/contador/iva/presentado', data={'mes': '2026-09', 'presentado': '1'})
        octubre = date(2026, 10, 1)
        self.assertEqual(estado_del_mes(octubre, 0, 0)['saldo_favor_anterior'], 20000)

        self.http.post('/contador/iva/ajustes', data={'mes': '2026-10', 'saldo_favor_anterior': '0',
                                                      'retenciones': '0'})

        estado = estado_del_mes(octubre, 0, 0)
        self.assertEqual(estado['saldo_favor_anterior'], 0)
        self.assertIsNone(estado['saldo_favor_sugerido'])
        self.http.post('/contador/iva/presentado', data={'mes': '2026-10', 'presentado': '1'})
        r = ContadorMes.query.filter_by(periodo='2026-10').one()
        self.assertEqual(float(r.saldo_favor_anterior), 0)

    def test_mes_abierto_no_sugiere(self):
        from app.services.contador_meses import saldo_favor_sugerido

        self.http.post('/contador/iva/ajustes', data={'mes': '2026-09', 'saldo_favor_anterior': '30.000',
                                                      'retenciones': '0'})

        self.assertIsNone(saldo_favor_sugerido(date(2026, 10, 1)))

    def test_ajustes_presentados_se_conservan_hasta_reabrir(self):
        from app.services.contador_meses import saldo_favor_sugerido

        self.http.post('/contador/iva/ajustes', data={
            'mes': '2026-09', 'saldo_favor_anterior': '30.000', 'retenciones': '0'})
        self.http.post('/contador/iva/presentado', data={'mes': '2026-09', 'presentado': '1'})
        respuesta = self.http.post('/contador/iva/ajustes', data={
            'mes': '2026-09', 'saldo_favor_anterior': '99.000', 'retenciones': '10.000'},
            follow_redirects=True)
        self.assertIn('Volvé a abrir el mes', respuesta.get_data(as_text=True))
        self.assertEqual(saldo_favor_sugerido(date(2026, 10, 1)), 30000)

        self.http.post('/contador/iva/presentado', data={'mes': '2026-09', 'presentado': '0'})
        self.http.post('/contador/iva/ajustes', data={
            'mes': '2026-09', 'saldo_favor_anterior': '99.000', 'retenciones': '10.000'})
        r = ContadorMes.query.filter_by(periodo='2026-09').one()
        self.assertEqual(float(r.retenciones), 10000)
        self.assertFalse(r.presentado)

    def test_montos_invalidos_no_rompen_ni_guardan_ajustes(self):
        for monto in ('NaN', 'Infinity', '1e100', '1.5', '1,234', '10000000000000', '-1'):
            with self.subTest(monto=monto):
                respuesta = self.http.post('/contador/iva/ajustes', data={
                    'mes': '2026-09', 'saldo_favor_anterior': monto, 'retenciones': '0'})
                self.assertEqual(respuesta.status_code, 302)
                self.assertEqual(ContadorMes.query.count(), 0)

    def test_formulario_no_redondea_los_ajustes_guardados(self):
        self.http.post('/contador/iva/ajustes', data={
            'mes': '2026-09', 'saldo_favor_anterior': '1.234,56', 'retenciones': '0,25'})
        html = self.http.get('/contador/iva?mes=2026-09').get_data(as_text=True)
        self.assertIn('value="1.234,56"', html)
        self.assertIn('value="0,25"', html)

    def test_documentos_de_prueba_no_generan_cierre_fiscal(self):
        from facturacion_electronica.models import FacturacionElectronicaConfig

        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'true')
        FacturacionElectronicaConfig.obtener().ambiente = 'test'
        db.session.commit()
        respuesta = self.http.post('/contador/iva/presentado', data={
            'mes': '2026-09', 'presentado': '1'}, follow_redirects=True)
        self.assertIn('no se puede marcar el mes', respuesta.get_data(as_text=True))
        self.assertEqual(ContadorMes.query.count(), 0)
