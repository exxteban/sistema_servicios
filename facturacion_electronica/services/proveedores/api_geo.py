"""Tabla geográfica del modo API: la de la SET que publica el proveedor.

El motor propio valida la ubicación contra la tabla que trae TIPS xmlgen, y
esa tabla es vieja: le faltan 21 distritos y 359 ciudades creados después
(Tavapy, Dr. Raúl Peña, Santa Rosa del Aguaray...). La API, desde su 1.8.0,
expone el código de referencia geográfica de la SET de noviembre de 2025 en
`GET /sifen/catalogs/{departments,districts,cities}/`. Por eso cada modo usa
la suya: el propio sigue con la de TIPS (`data/geo_sifen.json`) y el de API
con ésta.

Nunca se consulta en vivo desde la pantalla. La lista vive en un archivo de
la instancia y el job de FE la renueva cuando pasan `DIAS_VIGENCIA` días. Si
todavía no se descargó nunca, o la API no responde, se usa la copia que viaja
con el código (`data/geo_sifen_set.json`): la configuración nunca queda sin
lista por un problema de red.

Los nombres se cortan a 30 caracteres: es lo que acepta SIFEN en
`dDesDisEmi` / `dDesCiuEmi`, y 58 ciudades del catálogo oficial lo superan.
"""
import json
import os
import time
from datetime import datetime, timedelta
from functools import lru_cache

from flask import current_app, has_app_context

from facturacion_electronica.services.proveedores import api_client

DIAS_VIGENCIA = 30
# Tras un fallo no se reintenta en cada pasada del job (cada 5 minutos).
REINTENTO_TRAS_FALLO = timedelta(hours=1)
LARGO_NOMBRE_SIFEN = 30

_RUTA_SNAPSHOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'data', 'geo_sifen_set.json',
)
NOMBRE_ARCHIVO = 'fe_geo_sifen_api.json'

# Por proceso: la tabla leída (con el mtime del archivo) y el último intento fallido.
_cache = {'mtime': None, 'tabla': None}
_ultimo_fallo = {'cuando': None}


def _ruta_cache():
    """None fuera de una app (un script, una prueba suelta): queda la copia del código."""
    if not has_app_context():
        return None
    return os.path.join(current_app.instance_path, NOMBRE_ARCHIVO)


@lru_cache(maxsize=1)
def _snapshot():
    with open(_RUTA_SNAPSHOT, encoding='utf-8') as archivo:
        return json.load(archivo)


def _leer_cache():
    ruta = _ruta_cache()
    if ruta is None:
        return None
    try:
        mtime = os.path.getmtime(ruta)
    except OSError:
        return None
    if _cache['mtime'] != mtime:
        try:
            with open(ruta, encoding='utf-8') as archivo:
                _cache['tabla'] = json.load(archivo)
            _cache['mtime'] = mtime
        except (OSError, ValueError):
            return None
    return _cache['tabla']


def tabla():
    """La tabla del modo API: la descargada si hay, si no la copia del código."""
    return _leer_cache() or _snapshot()


def _nombre(valor):
    return str(valor or '').strip()[:LARGO_NOMBRE_SIFEN]


def descargar(config):
    """Baja la tabla completa de la API. Devuelve (tabla, error)."""
    base = '/sifen/catalogs'
    departamentos, error = api_client.solicitar(config, 'GET', f'{base}/departments/')
    if error:
        return None, error
    distritos, error = api_client.solicitar(config, 'GET', f'{base}/districts/')
    if error:
        return None, error

    ciudades = []
    # Las ciudades exigen un filtro: se piden por departamento (18 llamadas).
    for departamento in departamentos or []:
        filas, error = api_client.solicitar(
            config, 'GET', f"{base}/cities/?department={int(departamento['code'])}",
        )
        if error:
            return None, error
        ciudades.extend(filas or [])

    if not (departamentos and distritos and ciudades):
        return None, 'La API devolvió el catálogo geográfico vacío.'

    return {
        'fuente': 'API de facturación electrónica, /sifen/catalogs/',
        'actualizado': datetime.utcnow().isoformat(timespec='seconds'),
        'departamentos': [
            {'codigo': int(d['code']), 'descripcion': _nombre(d['description'])}
            for d in departamentos
        ],
        'distritos': [
            {'codigo': int(d['code']), 'descripcion': _nombre(d['description']),
             'departamento': int(d['department_code'])}
            for d in distritos
        ],
        'ciudades': [
            {'codigo': int(c['code']),
             'descripcion': _nombre(c.get('sifen_name') or c['description']),
             'distrito': int(c['district_code'])}
            for c in ciudades
        ],
    }, None


def _guardar(nueva):
    """Escritura atómica: otro proceso nunca lee un archivo a medio escribir."""
    ruta = _ruta_cache()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    temporal = f'{ruta}.{os.getpid()}.tmp'
    with open(temporal, 'w', encoding='utf-8') as archivo:
        json.dump(nueva, archivo, ensure_ascii=False, separators=(',', ':'))
    os.replace(temporal, ruta)


def vencida():
    try:
        edad = time.time() - os.path.getmtime(_ruta_cache())
    except (OSError, TypeError):
        return True
    return edad > DIAS_VIGENCIA * 86400


def actualizar_si_vencida(config):
    """Renueva la tabla guardada si pasó su vigencia. Devuelve un error o None.

    La llama el job de FE en cada pasada; casi siempre no hace nada. Sólo aplica
    al modo API con la URL cargada: sin eso no hay a quién pedirle la tabla.
    """
    from facturacion_electronica.services.proveedores import PROVEEDOR_API

    if getattr(config, 'proveedor', None) != PROVEEDOR_API or not api_client.base_url(config):
        return None
    if not vencida():
        return None
    fallo = _ultimo_fallo['cuando']
    if fallo is not None and datetime.utcnow() - fallo < REINTENTO_TRAS_FALLO:
        return None

    nueva, error = descargar(config)
    if error:
        _ultimo_fallo['cuando'] = datetime.utcnow()
        return error
    _guardar(nueva)
    _ultimo_fallo['cuando'] = None
    return None


__all__ = ['tabla', 'descargar', 'vencida', 'actualizar_si_vencida', 'DIAS_VIGENCIA']
