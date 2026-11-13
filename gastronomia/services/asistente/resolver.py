"""Resolucion de entidades por id o nombre para el asistente.

Lectura: tolerante (acepta un nombre parcial si hay un solo candidato).
Escritura: exacta (id o nombre completo). Un parcial podria cambiar el precio o la receta
de otro plato, asi que en ese caso se devuelve error con sugerencias para que la IA pregunte.
"""
from __future__ import annotations

import unicodedata

from gastronomia.models import GastronomiaCategoria, GastronomiaProducto
from gastronomia.services.stock_service import listar_insumos

MAX_SUGERENCIAS = 5


def normalizar(texto) -> str:
    base = unicodedata.normalize('NFKD', str(texto or ''))
    return ' '.join(''.join(c for c in base if not unicodedata.combining(c)).lower().split())


def _por_id(registros, valor, attr_id: str):
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int) or str(valor).strip().isdigit():
        for item in registros:
            if int(getattr(item, attr_id)) == int(valor):
                return item
    return None


def _exacto(registros, valor):
    clave = normalizar(valor)
    exactos = [item for item in registros if normalizar(item.nombre) == clave]
    return exactos[0] if exactos else None


def _parciales(registros, valor) -> list:
    clave = normalizar(valor)
    return [item for item in registros if clave and clave in normalizar(item.nombre)]


def _buscar(registros, valor, attr_id: str, exacto: bool = False):
    if valor in (None, ''):
        return None
    encontrado = _exacto(registros, valor) or _por_id(registros, valor, attr_id)
    if encontrado or exacto:
        return encontrado
    parciales = _parciales(registros, valor)
    return parciales[0] if len(parciales) == 1 else None


def _categorias(cliente_id: int):
    return GastronomiaCategoria.query.filter_by(cliente_id=int(cliente_id), activo=True).all()


def _platos(cliente_id: int):
    return GastronomiaProducto.query.filter_by(cliente_id=int(cliente_id), activo=True).all()


def categoria(cliente_id: int, valor, exacto: bool = False) -> GastronomiaCategoria | None:
    return _buscar(_categorias(cliente_id), valor, 'id_categoria', exacto)


def plato(cliente_id: int, valor, exacto: bool = False) -> GastronomiaProducto | None:
    return _buscar(_platos(cliente_id), valor, 'id_producto', exacto)


def insumo(cliente_id: int, valor, exacto: bool = False):
    return _buscar(listar_insumos(cliente_id), valor, 'id_producto', exacto)


def _no_encontrado(tipo: str, valor, registros) -> str:
    sugerencias = [item.nombre for item in _parciales(registros, valor)[:MAX_SUGERENCIAS]]
    base = f"No hay {tipo} llamado exactamente '{valor}'."
    if sugerencias:
        return f"{base} Parecidos: {', '.join(sugerencias)}. Pregunta al usuario cual es y usa el nombre exacto."
    return base


def plato_para_escribir(cliente_id: int, valor) -> GastronomiaProducto:
    registros = _platos(cliente_id)
    encontrado = _buscar(registros, valor, 'id_producto', exacto=True)
    if not encontrado:
        raise ValueError(_no_encontrado('un plato', valor, registros))
    return encontrado


def insumo_para_escribir(cliente_id: int, valor):
    registros = listar_insumos(cliente_id)
    encontrado = _buscar(registros, valor, 'id_producto', exacto=True)
    if not encontrado:
        raise ValueError(_no_encontrado('un insumo', valor, registros))
    return encontrado


def categoria_para_escribir(cliente_id: int, valor) -> GastronomiaCategoria:
    registros = _categorias(cliente_id)
    encontrado = _buscar(registros, valor, 'id_categoria', exacto=True)
    if not encontrado:
        raise ValueError(_no_encontrado('una categoria', valor, registros) + ' Si es nueva, creala primero.')
    return encontrado
