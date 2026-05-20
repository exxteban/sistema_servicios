"""
Servicios del asistente IA interno del backoffice.
"""

from app.services.ia_backoffice.security import (
    es_usuario_root,
    puede_gestionar_asistente_ia,
    puede_usar_asistente_ia,
)
from app.services.ia_backoffice.settings import (
    IA_BACKOFFICE_DEFAULTS,
    obtener_configuracion_asistente,
)

__all__ = [
    'IA_BACKOFFICE_DEFAULTS',
    'es_usuario_root',
    'obtener_configuracion_asistente',
    'puede_gestionar_asistente_ia',
    'puede_usar_asistente_ia',
]
