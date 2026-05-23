from flask import g, has_request_context
from sqlalchemy import and_, or_

from app.models import AgendaActividad, Configuracion, Usuario
from app.services.ia_backoffice.settings import CLAVE_SYSTEM_ROOT_USER_ID


def obtener_root_user_id_sistema():
    cache_key = '_agenda_root_user_id'
    if has_request_context() and hasattr(g, cache_key):
        return getattr(g, cache_key)
    raw_id = (Configuracion.obtener(CLAVE_SYSTEM_ROOT_USER_ID, '') or '').strip()
    try:
        root_id = int(raw_id)
    except (TypeError, ValueError):
        if has_request_context():
            setattr(g, cache_key, None)
        return None
    root_id = root_id if root_id > 0 else None
    if has_request_context():
        setattr(g, cache_key, root_id)
    return root_id


def es_usuario_root_sistema(usuario):
    root_id = obtener_root_user_id_sistema()
    if root_id and int(getattr(usuario, 'id_usuario', 0) or 0) == root_id:
        return True
    username = (getattr(usuario, 'username', '') or '').strip().lower()
    return username == 'root'


def filtro_mostrar_agenda_para_usuario(user_id: int):
    return or_(
        AgendaActividad.creado_por_id == user_id,
        AgendaActividad.mostrar_agenda_en == 'todos',
        and_(
            AgendaActividad.mostrar_agenda_en == 'solo_responsable',
            AgendaActividad.usuario_id == user_id,
        ),
        and_(
            AgendaActividad.mostrar_agenda_en == 'usuarios_especificos',
            AgendaActividad.usuarios_agenda.any(Usuario.id_usuario == user_id),
        ),
    )


def query_usuarios_agenda_visibles():
    query = Usuario.query.filter_by(activo=True)
    root_id = obtener_root_user_id_sistema()
    if root_id:
        query = query.filter(Usuario.id_usuario != root_id)
    return query.filter(Usuario.username != 'root').order_by(Usuario.nombre_completo.asc())


def usuarios_agenda_visibles_para(current_user, puede_ver_todo):
    if puede_ver_todo:
        return query_usuarios_agenda_visibles().all()
    if es_usuario_root_sistema(current_user):
        return []
    return [current_user]
