"""Datos del emisor en la API y el chequeo de `emission_readiness`.

Caso real (Janelipy, 2026-09-25): la actividad económica estaba cargada en
nuestra configuración pero no en la API, y la emisión rebotaba con 400
`company_missing_data`. Detrás había algo peor: el perfil de la API tenía sus
valores por defecto (persona física, sin dirección, departamento 11 con nombre
"CAPITAL", Asunción), y "Traer datos del emisor" los copiaba encima de los
datos reales.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import db
from facturacion_electronica.models import FacturacionElectronicaConfig

from test_facturacion_electronica_proveedor_base import BaseProveedorApi

SOLICITAR = 'facturacion_electronica.services.proveedores.api_client.solicitar'


def _config(**cambios):
    datos = dict(
        razon_social='Janelipy Group E.A.S.', tipo_contribuyente='2',
        actividad_economica_codigo='47723',
        actividad_economica_desc='Comercio al por menor de cosméticos',
        direccion='Ruta 1 km 20', numero_casa='123',
        departamento_codigo='12', departamento_desc='CENTRAL',
        distrito_codigo='', distrito_desc='',
        ciudad_codigo='6106', ciudad_desc='YPANE',
        telefono='0981123456', email='ventas@janelipy.com.py',
    )
    datos.update(cambios)
    return SimpleNamespace(**datos)


def test_arma_el_bloque_completo_del_emisor():
    from facturacion_electronica.services.proveedores.api_emisor import armar_datos_fiscales

    cuerpo, error = armar_datos_fiscales(_config())

    assert error is None
    assert cuerpo['taxpayer_type'] == 2
    assert cuerpo['address'] == 'Ruta 1 km 20'
    assert cuerpo['house_number'] == 123
    assert (cuerpo['department_code'], cuerpo['department_name']) == (12, 'CENTRAL')
    assert (cuerpo['city_code'], cuerpo['city_name']) == (6106, 'YPANE')
    assert cuerpo['district_code'] is None
    assert cuerpo['economic_activities'] == [
        {'code': '47723', 'description': 'Comercio al por menor de cosméticos'}]
    assert 'regime_type' not in cuerpo


def test_el_regimen_viaja_si_esta_cargado():
    """API 1.7.4: `regime_type` sale al XML como cTipReg."""
    from facturacion_electronica.services.proveedores.api_emisor import armar_datos_fiscales

    cuerpo, error = armar_datos_fiscales(_config(tipo_regimen='8'))

    assert error is None
    assert cuerpo['regime_type'] == 8


def test_lo_que_falta_se_lista_junto():
    from facturacion_electronica.services.proveedores.api_emisor import armar_datos_fiscales

    _cuerpo, error = armar_datos_fiscales(
        _config(direccion='', email='no tiene', ciudad_codigo='', telefono='12'))

    for falta in ('dirección', 'email válido', 'ciudad', 'teléfono'):
        assert falta in error

    _cuerpo, error = armar_datos_fiscales(_config(ruc='80178105', tipo_contribuyente='1'))
    assert 'persona jurídica' in error


def test_email_invalido_del_cliente_no_viaja():
    from facturacion_electronica.services.proveedores.api_payload import construir_receptor

    cliente = SimpleNamespace(id_cliente=7, ruc_ci='4281292', nombre='Alfio Oviedo',
                              email='no tiene')
    assert 'email' not in construir_receptor(cliente)
    cliente.email = 'alfio@correo.com'
    assert construir_receptor(cliente)['email'] == 'alfio@correo.com'


class TestDatosDelEmisorApi(BaseProveedorApi):
    def _config_completa(self):
        config = self._activar_api()
        for campo, valor in vars(_config()).items():
            setattr(config, campo, valor)
        db.session.commit()
        return config

    def _perfil_por_defecto(self, **extra):
        """Lo que devuelve la API para una empresa a la que nunca le cargaron nada."""
        perfil = self._perfil()
        perfil.update({
            'version': 7, 'address': '', 'taxpayer_type': 1,
            'department_code': 11, 'department_name': 'CAPITAL',
            'city_code': 1, 'city_name': 'Asunción',
            'economic_activities': [],
            'emission_readiness': {'ready': False, 'missing': ['economic_activities']},
        })
        perfil.update(extra)
        return perfil

    def test_sube_con_if_match_y_resincroniza(self):
        from facturacion_electronica.services.proveedores.api_emisor import cargar_datos_fiscales

        config = self._config_completa()
        llamadas = []

        def _solicitar(cfg, metodo, ruta, json=None, headers=None, **kwargs):
            llamadas.append((metodo, ruta, json, headers))
            if metodo == 'PUT':
                return {}, None
            if any(m == 'PUT' for m, *_ in llamadas):
                return self._perfil_por_defecto(
                    address='Ruta 1 km 20', taxpayer_type=2,
                    department_code=12, department_name='CENTRAL',
                    city_code=6106, city_name='YPANE',
                    emission_readiness={'ready': True, 'missing': []},
                ), None
            return self._perfil_por_defecto(), None

        with patch(SOLICITAR, _solicitar):
            resumen, error = cargar_datos_fiscales(config)

        self.assertIsNone(error)
        self.assertIn('Datos del emisor cargados', resumen)
        put = [ll for ll in llamadas if ll[0] == 'PUT'][0]
        self.assertEqual(put[3], {'If-Match': '7'})
        self.assertEqual(put[2]['department_code'], 12)
        config = FacturacionElectronicaConfig.obtener()
        self.assertEqual(config.tipo_contribuyente, '2')
        self.assertEqual(config.ciudad_codigo, '6106')

    def test_traer_datos_no_pisa_la_ubicacion_con_los_valores_por_defecto(self):
        from facturacion_electronica.services.proveedores.api_perfil import (
            aplicar_perfil_al_config,
        )

        config = self._config_completa()

        with patch(SOLICITAR, lambda *a, **k: (self._perfil_por_defecto(), None)):
            aplicar_perfil_al_config(config, self._perfil_por_defecto())

        config = FacturacionElectronicaConfig.obtener()
        self.assertEqual(config.tipo_contribuyente, '2')
        self.assertEqual(config.departamento_codigo, '12')
        self.assertEqual(config.ciudad_desc, 'YPANE')

    def test_sin_datos_en_la_api_frena_antes_de_reservar_numero(self):
        from facturacion_electronica.services.numeracion_service import peek_proximo_numero
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        proximo = peek_proximo_numero('001', '001')

        def _solicitar(cfg, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil_por_defecto(), None
            raise AssertionError(f'no se debe intentar el alta: {metodo} {ruta}')

        with patch(SOLICITAR, _solicitar):
            documento, error = emitir_para_pos(self._venta())

        self.assertIn('Actividad económica en la API', error)
        self.assertIn('Dirección y ubicación del emisor', error)
        self.assertIsNone(documento.numero)
        self.assertEqual(peek_proximo_numero('001', '001'), proximo)


if __name__ == '__main__':
    unittest.main()
