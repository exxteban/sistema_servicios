"""Transporte HTTP hacia la API externa de facturación electrónica.

Contrato: OpenAPI en `<base>/api/v1/schema/` (Swagger UI en `/api/v1/docs/`).
Autenticación: service token flow — `POST /auth/token/` con client_id +
client_secret devuelve un JWT de ~10 minutos y **sin refresh**. El token se
cachea en memoria del proceso y se renueva solo; un 401 fuerza una renovación
y un único reintento (el token pudo vencer entre que se leyó y se usó).

Como `sifen_client`, nada de acá lanza: todo devuelve (datos, error) y el
error ya viene en castellano, listo para mostrar.
"""
import threading
import time
from urllib.parse import urlsplit, urlunsplit

import requests

from facturacion_electronica.services.crypto import descifrar

TIMEOUT_SEGUNDOS = 20
# Emisión: firma + CDC + QR + validación XSD del otro lado.
TIMEOUT_EMISION_SEGUNDOS = 60
# El POS no puede cortar antes: si aborta, el cajero imprime el ticket normal
# y el alta igual puede completarse. Cubre emisión + token + perfil + margen.
TIMEOUT_POS_MARGEN_SEGUNDOS = 10
TIMEOUT_POS_SEGUNDOS = (
    TIMEOUT_EMISION_SEGUNDOS + (2 * TIMEOUT_SEGUNDOS) + TIMEOUT_POS_MARGEN_SEGUNDOS
)

# Margen para no usar un token que vence mientras viaja el request.
MARGEN_VENCIMIENTO_SEGUNDOS = 60

_TOKENS = {}
_CANDADO = threading.Lock()

ERROR_SIN_CONFIG = 'Falta configurar la URL y las credenciales de la API de facturación electrónica.'


def base_url(config):
    """Normaliza lo que haya cargado el usuario hasta la raíz de la v1.

    Se acepta tanto `https://host` como `https://host/api/v1` o la URL del
    Swagger que le pasaron por chat, que es lo que la gente copia y pega.
    Hay que separar fragmento y query: `.../docs/#/` no termina en `/docs`
    si se mira la URL cruda, y un rstrip deja el `#` pegado al path.
    """
    url = (getattr(config, 'api_url', '') or '').strip()
    if not url:
        return ''
    partes = urlsplit(url)
    path = (partes.path or '').rstrip('/')
    for sufijo in ('/docs', '/schema', '/redoc'):
        if path.endswith(sufijo):
            path = path[: -len(sufijo)].rstrip('/')
    if not path.endswith('/api/v1'):
        path = f'{path}/api/v1'
    return urlunsplit((partes.scheme, partes.netloc, path, '', ''))


def credenciales(config):
    """(client_id, client_secret) con el secreto ya descifrado."""
    client_id = (getattr(config, 'api_client_id', '') or '').strip()
    secreto = descifrar(getattr(config, 'api_credenciales', '') or '')
    return client_id, (secreto or '').strip()


def _clave_cache(config):
    client_id, _secreto = credenciales(config)
    return (base_url(config), client_id)


def olvidar_token(config=None):
    """Sin argumento vacía el cache entero: al guardar la configuración la clave
    ya cambió, así que borrar por clave nueva no sacaría la entrada vieja."""
    with _CANDADO:
        if config is None:
            _TOKENS.clear()
        else:
            _TOKENS.pop(_clave_cache(config), None)


def _detalle_error(respuesta):
    """Mensaje legible a partir del cuerpo de error de la API (DRF)."""
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return (respuesta.text or '').strip()[:300] or f'HTTP {respuesta.status_code}'

    if isinstance(cuerpo, dict):
        for clave in ('detail', 'error', 'message'):
            valor = cuerpo.get(clave)
            if isinstance(valor, str) and valor.strip():
                codigo = cuerpo.get('code')
                return f'{valor.strip()} ({codigo})' if codigo else valor.strip()
        partes = []
        for campo, valor in cuerpo.items():
            if isinstance(valor, list):
                valor = '; '.join(str(v) for v in valor)
            partes.append(f'{campo}: {valor}')
        return ' | '.join(partes)[:300]
    if isinstance(cuerpo, list):
        return '; '.join(str(v) for v in cuerpo)[:300]
    return str(cuerpo)[:300]


def obtener_token(config, forzar=False):
    """Devuelve (token, error). Cachea por (url, client_id) hasta su vencimiento."""
    url = base_url(config)
    client_id, secreto = credenciales(config)
    if not url or not client_id or not secreto:
        return None, ERROR_SIN_CONFIG

    clave = (url, client_id)
    ahora = time.time()
    if not forzar:
        with _CANDADO:
            cacheado = _TOKENS.get(clave)
        if cacheado and cacheado[1] > ahora:
            return cacheado[0], None

    try:
        respuesta = requests.post(
            f'{url}/auth/token/',
            json={'client_id': client_id, 'client_secret': secreto},
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.exceptions.ConnectionError:
        return None, ('No se pudo conectar con la API de facturación electrónica. '
                      'Verificá la URL y la conexión a internet.')
    except requests.exceptions.Timeout:
        return None, 'La API de facturación electrónica tardó demasiado en responder al autenticar.'
    except requests.exceptions.RequestException as exc:
        return None, f'Error al conectar con la API de facturación electrónica: {exc}'

    if respuesta.status_code == 401:
        return None, ('La API rechazó las credenciales (client_id / client_secret). '
                      'Revisalas en la configuración.')
    if respuesta.status_code == 429:
        return None, 'La API pidió esperar (demasiadas solicitudes). Se reintenta en la próxima pasada.'
    if respuesta.status_code != 200:
        return None, f'La API no emitió el token: {_detalle_error(respuesta)}'

    try:
        cuerpo = respuesta.json()
    except ValueError:
        return None, 'La API devolvió una respuesta de token ilegible.'

    token = (cuerpo.get('access_token') or '').strip()
    if not token:
        return None, 'La API devolvió un token vacío.'
    vence_en = cuerpo.get('expires_in') or 600
    try:
        vence_en = int(vence_en)
    except (TypeError, ValueError):
        vence_en = 600

    with _CANDADO:
        _TOKENS[clave] = (token, ahora + max(vence_en - MARGEN_VENCIMIENTO_SEGUNDOS, 30))
    return token, None


def solicitar(config, metodo, ruta, json=None, headers=None, timeout=None, binario=False):
    """Llamada autenticada a la API. Devuelve (datos, error).

    `datos` es el JSON de la respuesta, o los bytes crudos si `binario`.
    Un 204 devuelve {}. Cualquier error ya viene redactado para el usuario.
    """
    url = base_url(config)
    if not url:
        return None, ERROR_SIN_CONFIG

    token, error = obtener_token(config)
    if error:
        return None, error

    destino = f'{url}{ruta}'
    espera = timeout or TIMEOUT_SEGUNDOS

    def _llamar(token_actual):
        cabeceras = {'Authorization': f'Bearer {token_actual}'}
        if headers:
            cabeceras.update(headers)
        return requests.request(metodo, destino, json=json, headers=cabeceras, timeout=espera)

    try:
        respuesta = _llamar(token)
        if respuesta.status_code == 401:
            # El token pudo vencer entre el cache y el envío: se renueva una vez.
            token, error = obtener_token(config, forzar=True)
            if error:
                return None, error
            respuesta = _llamar(token)
    except requests.exceptions.ConnectionError:
        return None, ('No se pudo conectar con la API de facturación electrónica. '
                      'Verificá la URL y la conexión a internet.')
    except requests.exceptions.Timeout:
        return None, 'La API de facturación electrónica tardó demasiado en responder.'
    except requests.exceptions.RequestException as exc:
        return None, f'Error al conectar con la API de facturación electrónica: {exc}'

    if respuesta.status_code >= 400:
        return None, f'La API respondió {respuesta.status_code}: {_detalle_error(respuesta)}'

    if binario:
        return respuesta.content, None
    if respuesta.status_code == 204 or not (respuesta.content or b'').strip():
        return {}, None
    try:
        return respuesta.json(), None
    except ValueError:
        return None, 'La API devolvió una respuesta ilegible (no es JSON).'


__all__ = [
    'base_url', 'credenciales', 'obtener_token', 'olvidar_token', 'solicitar',
    'ERROR_SIN_CONFIG', 'TIMEOUT_SEGUNDOS', 'TIMEOUT_EMISION_SEGUNDOS',
    'TIMEOUT_POS_SEGUNDOS',
]
