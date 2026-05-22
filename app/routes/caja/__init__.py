"""
Rutas de gestión de caja
"""

from flask import Blueprint

caja_bp = Blueprint('caja', __name__)

from . import sesiones, cola_cobro, api, cierres, contabilidad, movimientos, cajas_admin, config_efectivo

__all__ = [
    'caja_bp',
    'sesiones',
    'cola_cobro',
    'api',
    'cierres',
    'contabilidad',
    'movimientos',
    'cajas_admin',
    'config_efectivo',
]
