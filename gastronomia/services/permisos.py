"""Permisos operativos del modulo Gastronomia."""
from __future__ import annotations

from functools import wraps

from flask import flash, jsonify, redirect, request, url_for
from flask_login import current_user


PERMISO_ACCESO = 'gastronomia_acceso'
PERMISO_MENU = 'gastronomia_menu'
PERMISO_POS = 'gastronomia_pos'
PERMISO_COCINA = 'gastronomia_cocina'
PERMISO_CAJA = 'gastronomia_caja'
PERMISO_SALON = 'gastronomia_salon'
PERMISO_REPORTES = 'gastronomia_reportes'


def tiene_permiso_gastronomia(*codigos: str) -> bool:
    if not current_user.is_authenticated:
        return False
    if getattr(current_user, 'es_admin', lambda: False)():
        return True
    requeridos = codigos or (PERMISO_ACCESO,)
    return any(getattr(current_user, 'tiene_permiso', lambda _codigo: False)(codigo) for codigo in requeridos)


def requiere_permiso_gastronomia(*codigos: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if tiene_permiso_gastronomia(*codigos):
                return func(*args, **kwargs)
            permiso = (codigos or (PERMISO_ACCESO,))[0]
            if _wants_json():
                return jsonify({
                    'error': 'Sin permisos',
                    'mensaje': 'No tienes permiso para acceder a esta funcion de Gastronomia.',
                    'permiso_requerido': permiso,
                }), 403
            flash('No tienes permiso para acceder a esta funcion de Gastronomia.', 'danger')
            return redirect(url_for('gastronomia.dashboard'))
        return wrapper
    return decorator


def _wants_json() -> bool:
    return (
        request.path.startswith('/api/')
        or request.is_json
        or 'application/json' in (request.headers.get('Accept') or '')
    )
