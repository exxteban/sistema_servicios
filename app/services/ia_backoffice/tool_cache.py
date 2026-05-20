"""
Cache corto para resultados de tools del asistente backoffice.
"""
from __future__ import annotations

import copy
import json
import time
from threading import RLock
from typing import Any


DEFAULT_TOOL_CACHE_TTL_SECONDS = 60
MAX_TOOL_CACHE_ENTRIES = 256

_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = RLock()


def _usuario_cache_key(usuario) -> str:
    if not usuario:
        return 'anon'
    id_usuario = getattr(usuario, 'id_usuario', None) or 'anon'
    id_rol = getattr(usuario, 'id_rol', None) or 'sin_rol'
    return f'u:{id_usuario}:r:{id_rol}'


def _argumentos_cache_key(argumentos: dict | None) -> str:
    try:
        return json.dumps(argumentos or {}, ensure_ascii=True, sort_keys=True, default=str, separators=(',', ':'))
    except Exception:
        return '{}'


def construir_cache_key(nombre: str, argumentos: dict | None, usuario) -> str:
    return f'{_usuario_cache_key(usuario)}:{nombre}:{_argumentos_cache_key(argumentos)}'


def obtener_tool_cache(nombre: str, argumentos: dict | None, usuario) -> dict[str, Any] | None:
    key = construir_cache_key(nombre, argumentos, usuario)
    ahora = time.monotonic()
    with _LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        vence_en, valor = item
        if vence_en <= ahora:
            _CACHE.pop(key, None)
            return None
        return copy.deepcopy(valor)


def guardar_tool_cache(
    nombre: str,
    argumentos: dict | None,
    usuario,
    resultado: dict[str, Any],
    *,
    ttl_seconds: int = DEFAULT_TOOL_CACHE_TTL_SECONDS,
) -> None:
    if ttl_seconds <= 0:
        return
    key = construir_cache_key(nombre, argumentos, usuario)
    vence_en = time.monotonic() + ttl_seconds
    with _LOCK:
        if len(_CACHE) >= MAX_TOOL_CACHE_ENTRIES:
            _purgar_cache_expirado()
        if len(_CACHE) >= MAX_TOOL_CACHE_ENTRIES:
            _CACHE.pop(next(iter(_CACHE)), None)
        _CACHE[key] = (vence_en, copy.deepcopy(resultado))


def _purgar_cache_expirado() -> None:
    ahora = time.monotonic()
    expiradas = [key for key, (vence_en, _valor) in _CACHE.items() if vence_en <= ahora]
    for key in expiradas:
        _CACHE.pop(key, None)


def limpiar_tool_cache() -> None:
    with _LOCK:
        _CACHE.clear()
