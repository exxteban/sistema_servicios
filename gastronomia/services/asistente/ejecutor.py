"""Ejecucion real de una tool del asistente (lectura o escritura) con manejo de errores."""
from __future__ import annotations

import logging

from app import db
from gastronomia.services.asistente.tools_escritura import TOOLS_ESCRITURA
from gastronomia.services.asistente.tools_lectura import TOOLS_LECTURA

logger = logging.getLogger(__name__)


def ejecutar_tool(nombre: str, args: dict, cliente_id: int, usuario_id: int | None) -> dict:
    try:
        if nombre in TOOLS_LECTURA:
            return {'ok': True, 'data': TOOLS_LECTURA[nombre](cliente_id, args)}
        if nombre == 'guardar_insumos':
            return {'ok': True, 'data': TOOLS_ESCRITURA[nombre](cliente_id, args, usuario_id=usuario_id)}
        if nombre in TOOLS_ESCRITURA:
            return {'ok': True, 'data': TOOLS_ESCRITURA[nombre](cliente_id, args)}
        return {'ok': False, 'error': 'tool_no_encontrada'}
    except (ValueError, TypeError) as exc:
        db.session.rollback()
        return {'ok': False, 'error': str(exc)}
    except Exception as exc:  # noqa: BLE001 - nunca romper el chat por una tool
        db.session.rollback()
        logger.exception('Error en tool %s del asistente gastronomia', nombre)
        return {'ok': False, 'error': type(exc).__name__}


def guardo_algo(resultado: dict) -> bool:
    """True solo si la tool de escritura realmente persistio algo (no si devolvio error o todo fallo)."""
    data = resultado.get('data') if resultado.get('ok') else None
    if not isinstance(data, dict) or data.get('error'):
        return False
    if 'hechos' in data:
        return any(not h.get('ya_existia') for h in data['hechos'] if isinstance(h, dict))
    if 'creadas' in data:
        return bool(data['creadas'])
    return True


def errores_de(resultado: dict) -> list[str]:
    if not resultado.get('ok'):
        return [str(resultado.get('error'))]
    data = resultado.get('data') or {}
    if not isinstance(data, dict):
        return []
    salida = [str(data['error'])] if data.get('error') else []
    salida += [str(d) for d in data.get('detalle') or []]
    salida += [f"faltan insumos: {', '.join(map(str, data['faltantes']))}"] if data.get('faltantes') else []
    salida += [f"{e.get('item')}: {e.get('error')}" for e in data.get('errores') or [] if isinstance(e, dict)]
    return salida
