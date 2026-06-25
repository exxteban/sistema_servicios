"""Tabla geográfica oficial de SIFEN (departamento/distrito/ciudad).

Los datos salen de la misma tabla que usa el validador de TIPS, exportada a
`data/geo_sifen.json`. Sirve para el selector en cascada y para completar las
descripciones a partir del código elegido.
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


@lru_cache(maxsize=1)
def _descripciones():
    data = _data()
    return (
        {d['codigo']: d['descripcion'] for d in data['departamentos']},
        {d['codigo']: d['descripcion'] for d in data['distritos']},
        {c['codigo']: c['descripcion'] for c in data['ciudades']},
    )


def _a_entero(codigo):
    try:
        return int(str(codigo).strip())
    except (TypeError, ValueError):
        return None


def departamentos():
    return sorted(_data()['departamentos'], key=lambda d: d['descripcion'])


def distritos_de(departamento_codigo):
    cod = _a_entero(departamento_codigo)
    if cod is None:
        return []
    return sorted(
        (d for d in _data()['distritos'] if d['departamento'] == cod),
        key=lambda d: d['descripcion'],
    )


def ciudades_de(distrito_codigo):
    cod = _a_entero(distrito_codigo)
    if cod is None:
        return []
    return sorted(
        (c for c in _data()['ciudades'] if c['distrito'] == cod),
        key=lambda c: c['descripcion'],
    )


def descripcion_departamento(codigo):
    return _descripciones()[0].get(_a_entero(codigo))


def descripcion_distrito(codigo):
    return _descripciones()[1].get(_a_entero(codigo))


def descripcion_ciudad(codigo):
    return _descripciones()[2].get(_a_entero(codigo))


__all__ = [
    'departamentos',
    'distritos_de',
    'ciudades_de',
    'descripcion_departamento',
    'descripcion_distrito',
    'descripcion_ciudad',
]
