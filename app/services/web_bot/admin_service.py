"""
Servicios de administración para conversaciones del bot web.
"""
from datetime import datetime
import json

from app import db
from app.models.web_bot import WebBotMensaje, WebBotSesion
from app.services.web_bot.session_policy import get_session_expires_at, is_session_expired


def build_web_bot_sessions_query(
    *,
    client_id: int | None = None,
    q: str = '',
    estado: str = '',
    slug: str = '',
):
    query = WebBotSesion.query
    if client_id:
        query = query.filter(WebBotSesion.id_cliente == client_id)

    clean_q = (q or '').strip()
    if clean_q:
        like = f'%{clean_q}%'
        query = query.filter(
            WebBotSesion.slug_tienda.ilike(like)
            | WebBotSesion.nombre_visitante.ilike(like)
            | WebBotSesion.email_visitante.ilike(like)
            | WebBotSesion.telefono_visitante.ilike(like)
            | WebBotSesion.session_token.ilike(like)
        )

    clean_estado = (estado or '').strip().lower()
    if clean_estado:
        query = query.filter(WebBotSesion.estado == clean_estado)

    clean_slug = (slug or '').strip().lower()
    if clean_slug:
        query = query.filter(WebBotSesion.slug_tienda == clean_slug)

    return query.order_by(WebBotSesion.ultima_actividad.desc(), WebBotSesion.id_sesion.desc())


def _parse_tool_payload(raw_value: str | None) -> dict | None:
    if not raw_value:
        return None
    try:
        data = json.loads(raw_value)
        return data if isinstance(data, dict) else {'raw': raw_value}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {'raw': raw_value}


def _format_safety_reason(reason: str | None) -> str:
    labels = {
        'sexual_or_abusive': 'Contenido sexual o abusivo',
        'technical_internal_request': 'Pedido tecnico interno',
        'internal_tool_disclosure': 'Pedido de tools internas',
        'session_blocked': 'Sesion bloqueada',
    }
    clean_reason = (reason or '').strip()
    return labels.get(clean_reason, clean_reason.replace('_', ' ').capitalize() if clean_reason else '')


def _extract_session_safety(metadata: dict | None) -> dict:
    raw_safety = metadata.get('safety') if isinstance(metadata, dict) else {}
    safety = raw_safety if isinstance(raw_safety, dict) else {}
    warning_count = int(safety.get('warning_count') or 0)
    last_reason = (safety.get('last_reason') or '').strip()
    last_violation_at = (safety.get('last_violation_at') or '').strip()
    last_admin_unlock_at = (safety.get('last_admin_unlock_at') or '').strip()
    last_admin_unlock_by = (safety.get('last_admin_unlock_by') or '').strip()
    return {
        'warning_count': warning_count,
        'blocked': bool(safety.get('blocked')),
        'last_reason': last_reason,
        'last_reason_label': _format_safety_reason(last_reason),
        'last_violation_at': last_violation_at,
        'last_admin_unlock_at': last_admin_unlock_at,
        'last_admin_unlock_by': last_admin_unlock_by,
    }


def serialize_web_bot_session_row(session: WebBotSesion) -> dict:
    metadata = _parse_tool_payload(session.metadata_json) or {}
    safety = _extract_session_safety(metadata)
    last_message = (
        session.mensajes
        .filter(WebBotMensaje.tipo_mensaje.in_(('text', 'note')))
        .order_by(WebBotMensaje.created_at.desc(), WebBotMensaje.id_mensaje.desc())
        .first()
    )
    total_messages = session.mensajes.count()
    total_tool_events = session.mensajes.filter(WebBotMensaje.tipo_mensaje == 'tool').count()
    expires_at = get_session_expires_at(session)
    return {
        'id': session.id_sesion,
        'id_cliente': session.id_cliente,
        'slug_tienda': session.slug_tienda,
        'session_token': session.session_token,
        'estado': session.estado,
        'origen': session.origen,
        'nombre_visitante': session.nombre_visitante or '',
        'telefono_visitante': session.telefono_visitante or '',
        'email_visitante': session.email_visitante or '',
        'fecha_creacion': session.fecha_creacion.isoformat() if session.fecha_creacion else None,
        'ultima_actividad': session.ultima_actividad.isoformat() if session.ultima_actividad else None,
        'expires_at': expires_at.isoformat() if expires_at else None,
        'expirada': is_session_expired(session),
        'total_mensajes': total_messages,
        'total_tools': total_tool_events,
        'ultimo_mensaje': (last_message.contenido or '') if last_message else '',
        'warning_count': safety['warning_count'],
        'blocked': safety['blocked'],
        'last_reason': safety['last_reason'],
        'last_reason_label': safety['last_reason_label'],
        'last_violation_at': safety['last_violation_at'],
    }


def serialize_web_bot_message(message: WebBotMensaje) -> dict:
    return {
        'id': message.id_mensaje,
        'direccion': message.direccion,
        'remitente': message.remitente,
        'tipo_mensaje': message.tipo_mensaje,
        'contenido': message.contenido,
        'created_at': message.created_at.isoformat() if message.created_at else None,
        'tool_payload': _parse_tool_payload(message.tool_call_json),
    }


def serialize_web_bot_session_detail(session: WebBotSesion) -> dict:
    metadata = _parse_tool_payload(session.metadata_json) or {}
    return {
        'session': serialize_web_bot_session_row(session),
        'metadata': metadata,
        'safety': _extract_session_safety(metadata),
        'messages': [
            serialize_web_bot_message(message)
            for message in session.mensajes.order_by(WebBotMensaje.created_at.asc(), WebBotMensaje.id_mensaje.asc()).all()
        ],
    }


def unlock_web_bot_session(session: WebBotSesion, actor_label: str = '') -> dict:
    metadata = _parse_tool_payload(session.metadata_json) or {}
    safety = metadata.get('safety') if isinstance(metadata.get('safety'), dict) else {}
    metadata['safety'] = safety
    safety['blocked'] = False
    safety['warning_count'] = 0
    safety['last_admin_unlock_at'] = datetime.utcnow().isoformat()
    safety['last_admin_unlock_by'] = (actor_label or '').strip()
    session.estado = 'bot'
    session.metadata_json = json.dumps(metadata, ensure_ascii=False, default=str)
    note_suffix = f' por {actor_label.strip()}' if (actor_label or '').strip() else ''
    db.session.add(WebBotMensaje(
        id_sesion=session.id_sesion,
        direccion='saliente',
        remitente='sistema',
        tipo_mensaje='note',
        contenido=f'Sesión desbloqueada manualmente desde admin{note_suffix}.',
        created_at=datetime.utcnow(),
    ))
    return serialize_web_bot_session_detail(session)
