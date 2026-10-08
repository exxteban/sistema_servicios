"""Tabla geográfica oficial de SIFEN (departamento/distrito/ciudad).

Hay dos, una por modo de emisión, y cada función recibe `proveedor` para
elegir:

- Motor propio (el default): la misma tabla que usa el validador de TIPS,
  exportada a `data/geo_sifen.json`. Es vieja, pero TIPS rechaza cualquier
  código que no esté en ella, así que ofrecer otros sería ofrecer un error.
- API: el código de referencia de la SET que publica el proveedor, guardado
  y renovado por `proveedores.api_geo`.

Sirve para el selector en cascada y para completar las descripciones a partir
del código elegido.
"""
import json
import os
from functools import lru_cache

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'data', 'geo_sifen.json'
)


@lru_cache(maxsize=1)
def _data():
    with open(_DATA_PATH, encoding='utf-8') as archivo:
        return json.load(archivo)


def _tabla(proveedor=None):
    from facturacion_electronica.services.proveedores import PROVEEDOR_API

    if proveedor == PROVEEDOR_API:
        from facturacion_electronica.services.proveedores import api_geo
        return api_geo.tabla()
    return _data()


def _descripcion(clave, codigo, proveedor):
    cod = _a_entero(codigo)
    return next((d['descripcion'] for d in _tabla(proveedor)[clave] if d['codigo'] == cod), None)


def _a_entero(codigo):
    try:
        return int(str(codigo).strip())
    except (TypeError, ValueError):
        return None


def departamentos(proveedor=None):
    return sorted(_tabla(proveedor)['departamentos'], key=lambda d: d['descripcion'])


def distritos_de(departamento_codigo, proveedor=None):
    cod = _a_entero(departamento_codigo)
    if cod is None:
        return []
    return sorted(
        (d for d in _tabla(proveedor)['distritos'] if d['departamento'] == cod),
        key=lambda d: d['descripcion'],
    )


def ciudades_de(distrito_codigo, proveedor=None):
    cod = _a_entero(distrito_codigo)
    if cod is None:
        return []
    return sorted(
        (c for c in _tabla(proveedor)['ciudades'] if c['distrito'] == cod),
        key=lambda c: c['descripcion'],
    )


def descripcion_departamento(codigo, proveedor=None):
    return _descripcion('departamentos', codigo, proveedor)


def descripcion_distrito(codigo, proveedor=None):
    return _descripcion('distritos', codigo, proveedor)


def descripcion_ciudad(codigo, proveedor=None):
    return _descripcion('ciudades', codigo, proveedor)


__all__ = [
    'departamentos',
    'distritos_de',
    'ciudades_de',
    'descripcion_departamento',
    'descripcion_distrito',
    'descripcion_ciudad',
]
