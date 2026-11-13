"""Resolucion tolerante de entidades por id o nombre para el asistente."""
from __future__ import annotations

import unicodedata

from gastronomia.models import GastronomiaCategoria, GastronomiaProducto
from gastronomia.services.stock_service import listar_insumos


def normalizar(texto) -> str:
    base = unicodedata.normalize('NFKD', str(texto or ''))
    return ' '.join(''.join(c for c in base if not unicodedata.combining(c)).lower().split())


def _buscar(registros, valor, attr_id: str):
    if valor in (None, ''):
        return None
    if isinstance(valor, int) or str(valor).strip().isdigit():
        for item in registros:
            if int(getattr(item, attr_id)) == int(valor):
                return item
    clave = normalizar(valor)
    exactos = [item for item in registros if normalizar(item.nombre) == clave]
    if exactos:
        return exactos[0]
    parciales = [item for item in registros if clave and clave in normalizar(item.nombre)]
    return parciales[0] if len(parciales) == 1 else None


def categoria(cliente_id: int, valor) -> GastronomiaCategoria | None:
    registros = GastronomiaCategoria.query.filter_by(cliente_id=int(cliente_id), activo=True).all()
    return _buscar(registros, valor, 'id_categoria')


def plato(cliente_id: int, valor) -> GastronomiaProducto | None:
    registros = GastronomiaProducto.query.filter_by(cliente_id=int(cliente_id), activo=True).all()
    return _buscar(registros, valor, 'id_producto')


def insumo(cliente_id: int, valor):
    return _buscar(listar_insumos(cliente_id), valor, 'id_producto')
