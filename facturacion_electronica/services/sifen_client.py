"""Cliente HTTP hacia el microservicio Node (TIPS) que genera/firma el XML.

El sistema Flask y el servicio Node están desacoplados: sólo se hablan por
HTTP. Si el servicio no está corriendo, se devuelve un error legible en vez
de romper la página.
"""
import os

import requests

URL_POR_DEFECTO = 'http://localhost:3010'
TIMEOUT_SEGUNDOS = 20


def _base_url():
    return (os.environ.get('SIFEN_SERVICE_URL') or URL_POR_DEFECTO).rstrip('/')


def _post_xml(path, payload):
    """POST a un endpoint del servicio que devuelve {xml} o {error}.
    Devuelve (xml, error); sólo uno tiene valor."""
    try:
        respuesta = requests.post(f'{_base_url()}{path}', json=payload, timeout=TIMEOUT_SEGUNDOS)
    except requests.exceptions.ConnectionError:
        return None, ('No se pudo conectar con el servicio de facturación electrónica. '
                      'Verificá que esté corriendo (sifen_service).')
    except requests.exceptions.Timeout:
        return None, 'El servicio de facturación electrónica tardó demasiado en responder.'

    if respuesta.status_code == 200:
        return respuesta.json().get('xml'), None

    try:
        detalle = respuesta.json().get('error') or respuesta.text
    except ValueError:
        detalle = respuesta.text
    return None, detalle


def generar_xml(params, data):
    return _post_xml('/generar', {'params': params, 'data': data})


def firmar_xml(xml, cert_path, password):
    return _post_xml('/firmar', {'xml': xml, 'certPath': cert_path, 'password': password})


__all__ = ['generar_xml', 'firmar_xml']
