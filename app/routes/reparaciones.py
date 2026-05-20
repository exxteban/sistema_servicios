"""
Compatibilidad de rutas de reparaciones
"""
from importlib import import_module
from pathlib import Path


__path__ = [str(Path(__file__).with_suffix(''))]

_base = import_module(__name__ + '.base')
import_module(__name__ + '.items')
import_module(__name__ + '.listado')
import_module(__name__ + '.formularios')
import_module(__name__ + '.detalle')
import_module(__name__ + '.tecnicos')
import_module(__name__ + '.seguimiento_admin')

reparaciones_bp = _base.reparaciones_bp

__all__ = [
    'reparaciones_bp',
]
