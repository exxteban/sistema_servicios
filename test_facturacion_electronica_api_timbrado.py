"""Carga de un timbrado en la API (`PUT /sifen/me/`) desde la configuración."""
from unittest.mock import patch

from facturacion_electronica.models import FacturacionElectronicaConfig
from facturacion_electronica.services.proveedores.api_timbrado import (
    armar_timbrado,
    armar_timbrados,
    cargar_timbrado,
    resolver_timbrado_nc,
)
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

    def test_manda_el_ambiente_elegido_y_avisa_que_espera_el_paso_a_produccion(self):
        config = self._activar_api()
        config.ruc = '80012345'
        puts = []

        def _solicitar(cfg, metodo, ruta, json=None, headers=None, **kwargs):
            if metodo == 'PUT':
                puts.append(json)
                return {}, None
            return self._perfil(), None

        with patch(SOLICITAR, _solicitar):
            resumen, error = cargar_timbrado(
                config, _form(timbrado_numero='19128252', tipo_documento='ambos', ambiente_api='prod'),
            )
        self.assertIsNone(error)
        self.assertEqual([s['environment'] for s in puts[0]['stamps']], ['prod', 'prod'])
        self.assertIn('de producción', resumen)
        self.assertIn('pase la empresa a producción', resumen)

    def test_no_carga_el_ruc_como_timbrado_de_produccion(self):
        config = self._activar_api()
        config.ruc = '80178105'
        with patch(SOLICITAR, side_effect=AssertionError('no debe llamar')):
            _r, error = cargar_timbrado(config, _form(ambiente_api='prod'))
        self.assertIn('timbrado de prueba', error)

    def test_un_formulario_invalido_no_llega_a_la_api(self):
        config = self._activar_api()
        with patch(SOLICITAR, side_effect=AssertionError('no debe llamar')):
            _r, error = cargar_timbrado(config, _form(timbrado_numero='123'))
        self.assertIn('8 dígitos', error)


def test_ambos_carga_factura_y_nc_con_el_mismo_numero():
    items, error = armar_timbrados(_form(tipo_documento='ambos', initial_number='35'))
    assert error is None
    assert [i['document_type'] for i in items] == [1, 5]
    assert {i['number'] for i in items} == {'80178105'}
    # El número inicial es el piso de las facturas; la NC numera aparte.
    assert items[0]['initial_number'] == '0000035'
    assert 'initial_number' not in items[1]


def test_sin_tipo_elegido_se_cargan_los_dos():
    items, _error = armar_timbrados(_form(tipo_documento=''))
    assert len(items) == 2


class TestResolverTimbradoNc(BaseProveedorApi):
    FACTURA = {'id': 'st-f', 'number': '80178105', 'establishment': '001',
               'expedition_point': '001', 'document_type': 1, 'valid_from': '2026-09-15'}

    def _perfil(self, stamps):
        return {'ruc': '', 'version': 3, 'sifen_mode': 'test', 'stamps': stamps}

    def test_copia_el_de_factura_si_no_hay_ninguno_de_nc(self):
        config = self._activar_api()
        puts = []

        def _solicitar(cfg, metodo, ruta, json=None, **kwargs):
            if metodo == 'PUT':
                puts.append(json)
                return {}, None
            stamps = [self.FACTURA]
            if puts:
                stamps.append(dict(self.FACTURA, id='st-nc', document_type=5))
            return self._perfil(stamps), None

        with patch(SOLICITAR, _solicitar):
            timbrado_id, error = resolver_timbrado_nc(config, self._perfil([self.FACTURA]))

        self.assertIsNone(error)
        self.assertEqual(timbrado_id, 'st-nc')
        self.assertEqual(puts[0]['stamps'][0]['document_type'], 5)
        self.assertEqual(puts[0]['stamps'][0]['number'], '80178105')

    def test_no_pisa_un_timbrado_de_nc_cargado_a_futuro(self):
        config = self._activar_api()
        futuro = dict(self.FACTURA, id='st-nc', document_type=5, valid_from='2099-01-01')
        with patch(SOLICITAR, side_effect=AssertionError('no debe llamar')):
            _id, error = resolver_timbrado_nc(config, self._perfil([self.FACTURA, futuro]))
        self.assertIn('vigente', error)

    def test_sin_factura_no_inventa_nada(self):
        config = self._activar_api()
        with patch(SOLICITAR, side_effect=AssertionError('no debe llamar')):
            _id, error = resolver_timbrado_nc(config, self._perfil([]))
        self.assertIn('ningún timbrado de nota de crédito', error)

    def test_sucursal_002_copia_el_suyo_aunque_la_001_ya_tenga_nc(self):
        # Mismo RUC y misma empresa en la API, una instalación por local.
        config = self._activar_api()
        config.establecimiento = '002'
        factura_002 = dict(self.FACTURA, id='st-f2', establishment='002')
        nc_001 = dict(self.FACTURA, id='st-nc1', document_type=5)
        puts = []

        def _solicitar(cfg, metodo, ruta, json=None, **kwargs):
            if metodo == 'PUT':
                puts.append(json)
                return {}, None
            stamps = [self.FACTURA, nc_001, factura_002]
            if puts:
                stamps.append(dict(factura_002, id='st-nc2', document_type=5))
            return self._perfil(stamps), None

        with patch(SOLICITAR, _solicitar):
            timbrado_id, error = resolver_timbrado_nc(
                config, self._perfil([self.FACTURA, nc_001, factura_002]),
            )

        self.assertIsNone(error)
        self.assertEqual(timbrado_id, 'st-nc2')
        copiado = puts[0]['stamps']
        self.assertEqual(len(copiado), 1)
        self.assertEqual((copiado[0]['establishment'], copiado[0]['expedition_point']), ('002', '001'))
