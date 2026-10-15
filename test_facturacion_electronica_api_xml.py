"""Copia local del XML firmado de los DE de la API (`proveedores.api_xml`)."""
from unittest.mock import patch

from app import db
from facturacion_electronica import ESTADO_APROBADO, ESTADO_CANCELADO, ESTADO_ENVIADO
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.proveedores import api_xml
from facturacion_electronica.services.proveedores.pertenencia import (
    emitido_por_api,
    emitido_por_motor_propio,
)
from test_facturacion_electronica_proveedor_base import BaseProveedorApi, xml_factura

DESCARGA = 'facturacion_electronica.services.proveedores.api_xml.descargar_xml'


class TestCopiaLocalXmlApi(BaseProveedorApi):
    def setUp(self):
        super().setUp()
        api_xml._fallidos.clear()
        self.addCleanup(api_xml._fallidos.clear)
        self.config = self._activar_api()

    def _documento(self, estado=ESTADO_APROBADO, api_id='d0c0ffee-0000-4000-8000-000000000001'):
        documento = DocumentoElectronico(
            id_venta=self._venta().id_venta, estado=estado, api_documento_id=api_id,
        )
        db.session.add(documento)
        db.session.commit()
        return documento

    def test_guarda_el_xml_de_un_aprobado_y_no_lo_vuelve_a_pedir(self):
        documento = self._documento()
        with patch(DESCARGA, return_value=(xml_factura(), None)) as descarga:
            self.assertEqual(api_xml.completar_copias(self.config), 1)
            self.assertEqual(api_xml.completar_copias(self.config), 0)
        self.assertEqual(descarga.call_count, 1)
        self.assertEqual(db.session.get(DocumentoElectronico, documento.id).xml_firmado, xml_factura())

    def test_tambien_copia_los_cancelados(self):
        documento = self._documento(estado=ESTADO_CANCELADO)
        with patch(DESCARGA, return_value=(xml_factura(), None)):
            api_xml.completar_copias(self.config)
        self.assertIsNotNone(documento.xml_firmado)

    def test_no_copia_lo_que_sifen_todavia_no_aprobo(self):
        """Un `correct/` cambia el XML: la copia quedaría distinta de la de SIFEN."""
        documento = self._documento(estado=ESTADO_ENVIADO)
        with patch(DESCARGA, return_value=(xml_factura(), None)) as descarga:
            api_xml.completar_copias(self.config)
            xml, error = api_xml.xml_del_documento(self.config, documento)
        self.assertIsNone(error)
        self.assertEqual(xml, xml_factura())
        self.assertEqual(descarga.call_count, 1)
        self.assertIsNone(documento.xml_firmado)

    def test_entrega_la_copia_local_sin_ir_a_la_api(self):
        documento = self._documento()
        documento.xml_firmado = '<rDE>local</rDE>'
        db.session.commit()
        with patch(DESCARGA) as descarga:
            xml, error = api_xml.xml_del_documento(self.config, documento)
        self.assertEqual((xml, error), ('<rDE>local</rDE>', None))
        descarga.assert_not_called()

    def test_la_descarga_manual_deja_la_copia_guardada(self):
        documento = self._documento()
        with patch(DESCARGA, return_value=(xml_factura(), None)):
            api_xml.xml_del_documento(self.config, documento)
        self.assertEqual(documento.xml_firmado, xml_factura())

    def test_un_xml_mas_grande_que_el_text_de_mysql_no_se_guarda_ni_se_repide(self):
        documento = self._documento()
        enorme = '<rDE>' + 'x' * api_xml.BYTES_MAXIMOS + '</rDE>'
        with patch(DESCARGA, return_value=(enorme, None)) as descarga:
            api_xml.completar_copias(self.config)
            api_xml.completar_copias(self.config)
        self.assertIsNone(documento.xml_firmado)
        self.assertEqual(descarga.call_count, 1)

    def test_si_la_api_no_responde_corta_la_pasada(self):
        self._documento(api_id='d0c0ffee-0000-4000-8000-000000000001')
        self._documento(api_id='d0c0ffee-0000-4000-8000-000000000002')
        with patch(DESCARGA, return_value=(None, 'La API no respondió.')) as descarga:
            self.assertEqual(api_xml.completar_copias(self.config), 0)
        self.assertEqual(descarga.call_count, 1)

    def test_con_el_motor_propio_no_hace_nada(self):
        self._documento()
        self.config.proveedor = 'propio'
        db.session.commit()
        with patch(DESCARGA) as descarga:
            self.assertEqual(api_xml.completar_copias(self.config), 0)
        descarga.assert_not_called()

    def test_de_punta_a_punta_por_http_scheduler_descarga_y_nc(self):
        """Sin simular `descargar_xml`: el job pide el XML por HTTP (token
        incluido), lo guarda, y después el botón y la NC lo leen sin red."""
        from types import SimpleNamespace

        from app.models import Usuario
        from facturacion_electronica.services import tareas_periodicas
        from facturacion_electronica.services.proveedores.api_nota_credito import armar_cuerpo_nc

        documento = self._documento()
        documento.cdc = '0' * 44
        db.session.commit()
        xml = xml_factura(ruc_ci='80012345-6', nombre='Comercial Ejemplo')
        pedidos = []

        def _token(url, json=None, timeout=None):
            return SimpleNamespace(status_code=200, json=lambda: {'access_token': 't', 'expires_in': 600})

        def _request(metodo, url, json=None, headers=None, timeout=None):
            pedidos.append((metodo, url))
            return SimpleNamespace(status_code=200, content=xml.encode('utf-8'))

        with patch('facturacion_electronica.services.proveedores.api_client.requests.post', _token), \
                patch('facturacion_electronica.services.proveedores.api_client.requests.request', _request), \
\
                patch('facturacion_electronica.services.tareas_periodicas.procesar_pendientes',
                      return_value={}), \
                patch('facturacion_electronica.services.proveedores.api_geo.actualizar_si_vencida',
                      return_value=None):
            tareas_periodicas.ejecutar()
        self.assertEqual(pedidos, [(
            'GET', f'https://api.ejemplo.test/api/v1/sifen/electronic-documents/{documento.api_documento_id}/xml/',
        )])
        self.assertEqual(db.session.get(DocumentoElectronico, documento.id).xml_firmado, xml)

        def _sin_red(*_a, **_k):
            raise AssertionError('no tenía que ir a la API')

        with patch('facturacion_electronica.services.proveedores.api_client.requests.request', _sin_red):
            cliente = self.app.test_client()
            admin = Usuario.query.filter_by(username='admin').first()
            with cliente.session_transaction() as sesion:
                sesion['_user_id'] = str(admin.id_usuario)
                sesion['_fresh'] = True
            respuesta = cliente.get(f'/facturacion-electronica/descargar/xml/{documento.id_venta}')
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.get_data(as_text=True), xml)
            self.assertIn(documento.cdc, respuesta.headers['Content-Disposition'])

            nc = SimpleNamespace(numero='0000001', nc_motivo=1, nc_motivo_desc='x',
                                 tipo_documento=5, id_devolucion=None, id_venta=documento.id_venta)
            cuerpo, error = armar_cuerpo_nc(self.config, nc, documento, SimpleNamespace(), [], 'uuid')
        self.assertIsNone(error)
        self.assertIn('80012345', str(cuerpo))

    def test_la_copia_no_lo_hace_pasar_por_documento_del_motor_propio(self):
        documento = self._documento()
        with patch(DESCARGA, return_value=(xml_factura(), None)):
            api_xml.completar_copias(self.config)
        self.assertTrue(emitido_por_api(documento))
        self.assertFalse(emitido_por_motor_propio(documento))
