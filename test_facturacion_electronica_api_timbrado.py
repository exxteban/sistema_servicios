"""Carga de un timbrado en la API (`PUT /sifen/me/`) desde la configuración."""
from unittest.mock import patch

from facturacion_electronica.models import FacturacionElectronicaConfig
from facturacion_electronica.services.proveedores.api_timbrado import armar_timbrado, cargar_timbrado
from test_facturacion_electronica_proveedor_base import BaseProveedorApi

SOLICITAR = 'facturacion_electronica.services.proveedores.api_client.solicitar'

FORM = {
    'tipo_documento': '1',
    'timbrado_numero': '80178105',
    'establecimiento': '1',
    'punto_expedicion': '001',
    'valid_from': '2026-09-15',
    'valid_to': '',
    'initial_number': '',
}


def _form(**cambios):
    datos = dict(FORM)
    datos.update(cambios)
    return datos


def test_arma_el_item_con_ceros_y_sin_opcionales_vacios():
    item, error = armar_timbrado(_form(initial_number='1'))
    assert error is None
    assert item == {
        'number': '80178105',
        'establishment': '001',
        'expedition_point': '001',
        'document_type': 1,
        'valid_from': '2026-09-15',
        'initial_number': '0000001',
    }


def test_valida_como_la_api_antes_de_mandar():
    casos = {
        'timbrado_numero': ('8017810', '8 dígitos'),
        'establecimiento': ('0001', '3 dígitos'),
        'tipo_documento': ('4', 'inválido'),
        'valid_from': ('', 'inicio'),
        'valid_to': ('2026-09-01', 'anterior'),
        'initial_number': ('0', '1 a 9999999'),
    }
    for campo, (valor, esperado) in casos.items():
        _item, error = armar_timbrado(_form(**{campo: valor}))
        assert esperado in (error or ''), campo


class TestCargarTimbradoApi(BaseProveedorApi):
    def _perfil(self, version=7, stamps=None):
        return {
            'ruc': '80012345', 'dv': '7', 'legal_name': 'Emisor de prueba',
            'sifen_mode': 'test', 'sifen_mode_display': 'Test',
            'version': version, 'stamps': stamps or [],
        }

    def test_manda_if_match_y_resincroniza(self):
        config = self._activar_api()
        config.ruc = '80012345'
        llamadas = []
        cargado = {'id': 'st-1', 'number': '80178105', 'establishment': '001',
                   'expedition_point': '001', 'document_type': 1, 'valid_from': '2026-09-15'}

        def _solicitar(cfg, metodo, ruta, json=None, headers=None, **kwargs):
            llamadas.append((metodo, ruta, json, headers))
            if metodo == 'PUT':
                return {}, None
            ya_subido = any(m == 'PUT' for m, *_ in llamadas)
            return self._perfil(stamps=[cargado] if ya_subido else []), None

        with patch(SOLICITAR, _solicitar):
            resumen, error = cargar_timbrado(config, _form())

        self.assertIsNone(error)
        self.assertIn('80178105', resumen)
        put = [ll for ll in llamadas if ll[0] == 'PUT'][0]
        self.assertEqual(put[1], '/sifen/me/')
        self.assertEqual(put[3], {'If-Match': '7'})
        self.assertEqual(put[2]['stamps'][0]['number'], '80178105')
        self.assertEqual(FacturacionElectronicaConfig.obtener().timbrado_numero, '80178105')

    def test_el_rechazo_de_la_api_se_muestra(self):
        config = self._activar_api()

        def _solicitar(cfg, metodo, ruta, **kwargs):
            if metodo == 'PUT':
                return None, 'La API respondió 409: profile_version_conflict'
            return self._perfil(), None

        with patch(SOLICITAR, _solicitar):
            _r, error = cargar_timbrado(config, _form())
        self.assertIn('409', error)

    def test_un_formulario_invalido_no_llega_a_la_api(self):
        config = self._activar_api()
        with patch(SOLICITAR, side_effect=AssertionError('no debe llamar')):
            _r, error = cargar_timbrado(config, _form(timbrado_numero='123'))
        self.assertIn('8 dígitos', error)
