"""
Reglas de seguridad del asistente IA interno.
"""
import os

from flask_login import current_user

from app.models import Configuracion
from app.services.ia_backoffice.settings import CLAVE_SYSTEM_ROOT_USER_ID


PERMISO_USAR_ASISTENTE = 'usar_asistente_ia'
PERMISO_GESTIONAR_ASISTENTE = 'gestionar_asistente_ia'


def es_usuario_root(user=None) -> bool:
    usuario = user if user is not None else current_user
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'activo', True) is False:
        return False

    root_id_raw = (Configuracion.obtener(CLAVE_SYSTEM_ROOT_USER_ID, '') or '').strip()
    if root_id_raw:
        try:
            return int(getattr(usuario, 'id_usuario', 0) or 0) == int(root_id_raw)
        except (TypeError, ValueError):
            return False

    root_username = (os.environ.get('APP_BOOTSTRAP_ROOT_USERNAME') or 'root').strip().lower() or 'root'
    username = (getattr(usuario, 'username', '') or '').strip().lower()
    return username == root_username


def puede_gestionar_asistente_ia(user=None) -> bool:
    usuario = user if user is not None else current_user
    return bool(
        es_usuario_root(usuario)
        and getattr(usuario, 'tiene_permiso', lambda _codigo: False)(PERMISO_GESTIONAR_ASISTENTE)
    )


def puede_usar_asistente_ia(user=None) -> bool:
    usuario = user if user is not None else current_user
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if es_usuario_root(usuario):
        return True
    return bool(getattr(usuario, 'tiene_permiso', lambda _codigo: False)(PERMISO_USAR_ASISTENTE))
