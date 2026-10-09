"""La línea `[FE-API]` que deja cada llamada a la API de FE.

Sin ella, un 409 o un 422 de configuración sólo quedaba en el documento (el
último intento) o en ningún lado, y diagnosticar pedía capturas de pantalla.
"""
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

from facturacion_electronica.services.proveedores import api_client

MODULO = 'facturacion_electronica.services.proveedores.api_client'


def _config():
    return SimpleNamespace(api_url='https://fe.example.com', api_client_id='cli')


def _respuesta(status, cuerpo=None):
    respuesta = MagicMock()
    respuesta.status_code = status
    respuesta.json.return_value = cuerpo if cuerpo is not None else {}
    respuesta.content = b'{}'
    respuesta.text = '{}'
    return respuesta


def _llamar(respuesta=None, excepcion=None, json=None):
    api_client.olvidar_token()
    token = _respuesta(200, {'access_token': 'tok-secreto', 'expires_in': 600})
    with patch(f'{MODULO}.credenciales', return_value=('cli', 'secreto')), \
            patch(f'{MODULO}.requests.post', return_value=token), \
            patch(f'{MODULO}.requests.request', return_value=respuesta, side_effect=excepcion):
        return api_client.solicitar(_config(), 'PUT', '/sifen/me/certificate/', json=json)


def test_error_de_la_api_queda_en_el_log_con_su_codigo(caplog):
    conflicto = _respuesta(409, {'error': {'code': 'external_ref_conflict', 'detail': 'Ya existe'}})
    with caplog.at_level(logging.INFO, logger=MODULO):
        _datos, error = _llamar(conflicto)

    assert 'external_ref_conflict' in error
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(avisos) == 1
    linea = avisos[0].getMessage()
    assert linea.startswith('[FE-API] PUT /sifen/me/certificate/ -> 409')
    assert 'external_ref_conflict' in linea


def test_llamada_exitosa_deja_linea_info():
    registros = []
    with patch(f'{MODULO}._log') as log:
        log.info.side_effect = lambda *a: registros.append(a)
        _llamar(_respuesta(200, {'ok': True}))

    assert any(a[1] == 'POST' and a[2] == '/auth/token/' for a in registros)
    assert any(a[1] == 'PUT' and a[3] == 200 for a in registros)
    log.warning.assert_not_called()


def test_timeout_queda_en_el_log(caplog):
    with caplog.at_level(logging.WARNING, logger=MODULO):
        _datos, error = _llamar(excepcion=requests.exceptions.Timeout())

    assert error
    assert any('-> timeout' in r.getMessage() for r in caplog.records)


def test_nunca_loguea_el_cuerpo_ni_el_token(caplog):
    cuerpo = {'p12_base64': 'CERTIFICADO-EN-BASE64', 'password': 'clave-del-cert'}
    with caplog.at_level(logging.DEBUG, logger=MODULO):
        _llamar(_respuesta(422, {'error': {'code': 'cert_ruc_mismatch'}}), json=cuerpo)

    texto = ' '.join(r.getMessage() for r in caplog.records)
    for secreto in ('CERTIFICADO-EN-BASE64', 'clave-del-cert', 'tok-secreto', 'secreto'):
        assert secreto not in texto
