"""Timbrado vigente, certificado/CSC remotos y timeout del POS vs el servidor."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from facturacion_electronica.models import FacturacionElectronicaConfig
from facturacion_electronica.services import validar_configuracion, validar_readiness
from facturacion_electronica.services.proveedores.api_client import (
    TIMEOUT_EMISION_SEGUNDOS,
    TIMEOUT_POS_SEGUNDOS,
)
from facturacion_electronica.services.proveedores.api_perfil import (
    olvidar_perfil,
    resolver_timbrado,
    seleccionar_timbrado,
)


def _config_punto():
    return SimpleNamespace(establecimiento='001', punto_expedicion='001')


def _stamp(**extra):
    base = {
        'id': 'aaaaaaaa-0000-4000-8000-000000000001',
        'number': '12345678',
        'establishment': '001',
        'expedition_point': '001',
        'document_type': 1,
        'valid_from': '2026-01-01',
    }
    base.update(extra)
    return base


def test_el_timeout_del_pos_cubre_el_de_emision():
    assert TIMEOUT_POS_SEGUNDOS > TIMEOUT_EMISION_SEGUNDOS


def test_resolver_timbrado_elige_el_valid_from_mas_reciente():
    """StampProfile no tiene valid_to: en una renovación no vale el primero de la lista."""
    perfil = {
        'stamps': [
            _stamp(id='viejo', number='11111111', valid_from='2024-01-01'),
            _stamp(id='nuevo', number='22222222', valid_from='2026-01-01'),
        ]
    }
    stamp_id, error = resolver_timbrado(_config_punto(), perfil)
    assert error is None
    assert stamp_id == 'nuevo'


def test_resolver_timbrado_ignora_el_que_todavia_no_empezo():
    perfil = {
        'stamps': [
            _stamp(id='futuro', number='99999999', valid_from='2099-01-01'),
            _stamp(id='vigente', number='11111111', valid_from='2024-01-01'),
        ]
    }
    stamp_id, error = resolver_timbrado(_config_punto(), perfil, hoy=date(2026, 9, 20))
    assert error is None
    assert stamp_id == 'vigente'


def test_resolver_timbrado_sin_vigente_lo_dice():
    perfil = {'stamps': [_stamp(id='futuro', valid_from='2099-01-01')]}
    stamp_id, error = resolver_timbrado(_config_punto(), perfil)
    assert stamp_id is None
    assert 'vigente' in (error or '').lower()


def test_seleccionar_timbrado_desempata_por_numero():
    perfil = {
        'stamps': [
            _stamp(id='a', number='10000000', valid_from='2026-01-01'),
            _stamp(id='b', number='20000000', valid_from='2026-01-01'),
        ]
    }
    elegido, _del_punto, _otros = seleccionar_timbrado(
        perfil, '001', '001', 1, hoy=date(2026, 6, 1),
    )
    assert elegido['id'] == 'b'


def test_en_produccion_ignora_el_timbrado_de_prueba_aunque_empate():
    """Janelipy: el de prueba (RUC sin DV) y el real con el mismo inicio; ganaba el de prueba."""
    perfil = {
        'ruc': '80178105', 'sifen_mode': 'production', 'environment': 'prod',
        'stamps': [
            _stamp(id='prueba', number='80178105', valid_from='2026-09-15', environment='prod'),
            _stamp(id='real', number='19128252', valid_from='2026-09-15', environment='prod'),
        ],
    }
    stamp_id, error = resolver_timbrado(_config_punto(), perfil, hoy=date(2026, 10, 5))
    assert error is None
    assert stamp_id == 'real'


def test_elige_solo_timbrados_del_ambiente_de_la_empresa():
    stamps = [
        _stamp(id='de-test', number='80178105', valid_from='2026-09-01', environment='test'),
        _stamp(id='de-prod', number='19128252', valid_from='2026-09-15', environment='prod'),
    ]
    en_test = {'ruc': '80178105', 'environment': 'test', 'stamps': stamps}
    en_prod = {'ruc': '80178105', 'environment': 'prod', 'stamps': stamps}
    hoy = date(2026, 10, 5)
    assert resolver_timbrado(_config_punto(), en_test, hoy=hoy)[0] == 'de-test'
    assert resolver_timbrado(_config_punto(), en_prod, hoy=hoy)[0] == 'de-prod'


def test_en_produccion_sin_timbrado_prod_explica_que_falta_cargarlo():
    perfil = {
        'ruc': '80178105', 'environment': 'prod',
        'stamps': [_stamp(number='19128252', valid_from='2026-09-15', environment='test')],
    }
    stamp_id, error = resolver_timbrado(_config_punto(), perfil, hoy=date(2026, 10, 5))
    assert stamp_id is None
    assert 'Producción' in error and '19128252' in error


def test_ignora_timbrados_inactivos():
    perfil = {'stamps': [
        _stamp(id='activo', number='11111111', valid_from='2024-01-01'),
        _stamp(id='inactivo', number='22222222', valid_from='2026-01-01', is_active=False),
    ]}
    assert resolver_timbrado(_config_punto(), perfil, hoy=date(2026, 6, 1))[0] == 'activo'


def _config_api():
    return FacturacionElectronicaConfig(
        id=1, proveedor='api', establecimiento='001', punto_expedicion='001',
        api_url='https://api.ejemplo.test', api_client_id='cli',
        api_credenciales='secreto',
    )


def test_validacion_api_exige_certificado_y_csc_remotos():
    config = FacturacionElectronicaConfig(
        id=1, proveedor='api', establecimiento='001', punto_expedicion='001',
        api_url='https://api.ejemplo.test', api_client_id='cli',
        api_credenciales='secreto',
    )
    perfil = {
        'ruc': '',
        'stamps': [],
        'sifen_config': {'certificate': None, 'csc': 'missing'},
    }
    olvidar_perfil()
    with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
               lambda *a, **k: (perfil, None)):
        faltantes = validar_readiness(config)
    assert 'Certificado digital en la API' in faltantes
    assert 'CSC en la API' in faltantes


def test_validar_configuracion_no_pega_a_la_red():
    """Es la compuerta del POS y del job: con la API caída tiene que contestar igual.

    Preguntarle el certificado y el CSC al proveedor acá apagaba las dos cosas
    en silencio cuando su servicio no contestaba (y el POS tardaba los dos
    timeouts en abrir). Ese chequeo vive en `validar_readiness`.
    """
    config = _config_api()
    llamadas = []

    def _solicitar(config_, metodo, ruta, **kwargs):
        llamadas.append((metodo, ruta))
        return None, 'No se pudo conectar con la API de facturación electrónica.'

    olvidar_perfil()
    with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
               _solicitar):
        faltantes = validar_configuracion(config)

    assert llamadas == []
    assert faltantes == []


def test_readiness_informa_cuando_no_pudo_preguntarle_al_proveedor():
    """La pantalla sí espera, y tiene que decir por qué no sabe."""
    config = _config_api()

    olvidar_perfil()
    with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
               lambda *a, **k: (None, 'La API tardó demasiado en responder.')):
        faltantes = validar_readiness(config)

    assert any('Perfil del emisor en la API' in f for f in faltantes)
