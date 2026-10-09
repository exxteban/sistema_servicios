"""Cliente HTTP hacia el microservicio Node (TIPS) que genera/firma el XML.

El sistema Flask y el servicio Node están desacoplados: sólo se hablan por
HTTP. Si el servicio no está corriendo, se devuelve un error legible en vez
de romper la página.
"""
import os

import requests

URL_POR_DEFECTO = 'http://localhost:3010'
TIMEOUT_SEGUNDOS = 20
# El envío/consulta a SIFEN puede tardar; el servicio Node usa 90s internos.
TIMEOUT_ENVIO_SEGUNDOS = 100


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


def generar_qr(xml_firmado, id_csc, csc, ambiente):
    """Agrega el nodo gCamFuFD/dCarQR al XML firmado. Devuelve (xml_con_qr, error)."""
    return _post_xml('/qr', {'xml': xml_firmado, 'idCSC': id_csc, 'csc': csc, 'env': ambiente})


def _post_largo(path, payload):
    """POST con el timeout de envío a SIFEN. Devuelve (json_dict, error)."""
    try:
        respuesta = requests.post(f'{_base_url()}{path}', json=payload, timeout=TIMEOUT_ENVIO_SEGUNDOS)
    except requests.exceptions.ConnectionError:
        return None, ('No se pudo conectar con el servicio de facturación electrónica. '
                      'Verificá que esté corriendo (sifen_service).')
    except requests.exceptions.Timeout:
        return None, 'SIFEN tardó demasiado en responder.'

    if respuesta.status_code == 200:
        return respuesta.json(), None

    try:
        detalle = respuesta.json().get('error') or respuesta.text
    except ValueError:
        detalle = respuesta.text
    return None, detalle


def _post_json(path, payload):
    """POST a un endpoint que devuelve {respuesta}. Devuelve (respuesta, error)."""
    cuerpo, error = _post_largo(path, payload)
    if error:
        return None, error
    return cuerpo.get('respuesta'), None


def enviar_de(xml_firmado, cert_path, password, env, request_id=None):
    """Envía el DE a SIFEN (siRecepDE). Devuelve (respuesta, error)."""
    return _post_json('/enviar', {
        'xml': xml_firmado, 'certPath': cert_path, 'password': password,
        'env': env, 'id': request_id,
    })


def enviar_lote(xmls, cert_path, password, env, request_id=None):
    """Envía uno o más DE en un lote (siRecepLoteDE). Devuelve (respuesta, error).

    SIFEN contesta sólo que recibió el lote y su número (`dProtConsLote`); el
    resultado de cada DE se pide después con `consultar_lote`.
    """
    return _post_json('/enviar-lote', {
        'xmls': list(xmls), 'certPath': cert_path, 'password': password,
        'env': env, 'id': request_id,
    })


def consultar_lote(numero_lote, cert_path, password, env, request_id=None):
    """Resultado de un lote enviado (siConsLoteDE). Devuelve (respuesta, error)."""
    return _post_json('/consultar-lote', {
        'numeroLote': numero_lote, 'certPath': cert_path, 'password': password,
        'env': env, 'id': request_id,
    })


def consultar_de(cdc, cert_path, password, env, request_id=None):
    """Consulta el estado de un DE por CDC (siConsDE). Devuelve (respuesta, error)."""
    return _post_json('/consultar', {
        'cdc': cdc, 'certPath': cert_path, 'password': password,
        'env': env, 'id': request_id,
    })


def cancelar_de(params, cdc, motivo, cert_path, password, env, request_id=None,
                fecha_firma=None):
    """Cancela un DE aprobado (evento). Devuelve (respuesta, xml_firmado, error).

    `fecha_firma` es la hora **local de Paraguay** con formato
    `YYYY-MM-DDTHH:MM:SS`. Va explícita porque `dFecFirma` lo escribe la
    librería con `new Date()` y lo formatea con la hora local **del proceso
    Node**: en un servidor en UTC el evento sale firmado tres horas en el
    futuro y SIFEN lo rechaza sin decir por qué.
    """
    cuerpo, error = _post_largo('/cancelar', {
        'params': params, 'cdc': cdc, 'motivo': motivo,
        'certPath': cert_path, 'password': password, 'env': env, 'id': request_id,
        'fechaFirma': fecha_firma,
    })
    if error:
        return None, None, error
    return cuerpo.get('respuesta'), cuerpo.get('xml'), None


def inutilizar_de(params, data, cert_path, password, env, request_id=None,
                  fecha_firma=None):
    """Informa a SIFEN un rango de números que no se van a usar (evento).

    `data` lleva timbrado, establecimiento, punto, desde, hasta, tipoDocumento
    y motivo. A diferencia de la cancelación no hay CDC: el documento nunca
    llegó a SIFEN, lo que se da de baja es el número dentro del timbrado.

    `fecha_firma` va por el mismo motivo que en `cancelar_de`.
    """
    cuerpo, error = _post_largo('/inutilizar', {
        'params': params, 'data': data,
        'certPath': cert_path, 'password': password, 'env': env, 'id': request_id,
        'fechaFirma': fecha_firma,
    })
    if error:
        return None, None, error
    return cuerpo.get('respuesta'), cuerpo.get('xml'), None


__all__ = ['generar_xml', 'firmar_xml', 'generar_qr', 'enviar_de', 'consultar_de',
           'enviar_lote', 'consultar_lote', 'cancelar_de', 'inutilizar_de']
