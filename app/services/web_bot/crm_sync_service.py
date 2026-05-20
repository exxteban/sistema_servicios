"""
Sincronización incremental entre sesiones del bot web y el historial CRM/WhatsApp.
"""
import json
from datetime import datetime

from app import db
from app.models.web_bot import WebBotMensaje, WebBotSesion
from app.models.whatsapp import WhatsAppConversacion, WhatsAppMensaje
from app.utils.phone_utils import formatear_telefono_display, normalizar_telefono


VISIBLE_SYNC_MESSAGE_TYPES = {'text', 'note'}
SYNC_STATE_KEY = 'crm_sync'


def _parse_metadata(raw_value: str | None) -> dict:
    try:
        data = json.loads(raw_value or '{}')
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _persist_metadata(session: WebBotSesion, metadata: dict) -> dict:
    session.metadata_json = json.dumps(metadata or {}, ensure_ascii=False, default=str)
    return metadata


def _sync_state(metadata: dict) -> dict:
    state = metadata.get(SYNC_STATE_KEY)
    return state if isinstance(state, dict) else {}


def _session_phone(session: WebBotSesion) -> str:
    telefono = normalizar_telefono(session.telefono_visitante or '')
    return telefono or f'WBS-{session.id_sesion}'


def _session_name(session: WebBotSesion, queue_phone: str) -> str:
    nombre = (session.nombre_visitante or '').strip()
    if nombre:
        return nombre

    telefono = normalizar_telefono(session.telefono_visitante or '') or queue_phone
    if telefono.startswith('WBS-'):
        return f'Bot Web {session.slug_tienda}'
    return f'Web {formatear_telefono_display(telefono)}'


def _pending_handoff_token(session: WebBotSesion) -> str:
    handoff = session.handoffs.filter_by(estado='generado').first()
    return (handoff.handoff_token or '') if handoff else ''


def _session_preview(session: WebBotSesion, max_messages: int = 40) -> list[dict]:
    mensajes = (
        session.mensajes
        .filter(WebBotMensaje.tipo_mensaje.in_(tuple(VISIBLE_SYNC_MESSAGE_TYPES)))
        .order_by(WebBotMensaje.created_at.desc(), WebBotMensaje.id_mensaje.desc())
        .limit(max(1, max_messages))
        .all()
    )
    preview = []
    for msg in reversed(mensajes):
        contenido = (msg.contenido or '').strip()
        if not contenido:
            continue
        preview.append({
            'direccion': msg.direccion,
            'remitente': msg.remitente,
            'contenido': contenido[:500],
            'created_at': msg.created_at.isoformat() if msg.created_at else None,
        })
    return preview


def _build_context_payload(session: WebBotSesion, handoff_token: str) -> dict:
    visitante = {
        'nombre': session.nombre_visitante or '',
        'telefono': normalizar_telefono(session.telefono_visitante or '') or '',
        'email': session.email_visitante or '',
    }
    return {
        'web_bot': {
            'origen': session.origen or 'tienda_widget',
            'canal_origen': 'web',
            'label': 'Bot tienda',
            'handoff_token': handoff_token,
            'id_sesion_web': session.id_sesion,
            'slug_tienda': session.slug_tienda,
        },
        'web_chat': {
            'session_token': session.session_token,
            'estado': session.estado,
            'preview': _session_preview(session),
            'visitante': visitante,
        },
    }


def _merge_context(conversacion: WhatsAppConversacion, session: WebBotSesion, handoff_token: str):
    try:
        contexto = json.loads(conversacion.contexto or '{}')
        contexto = contexto if isinstance(contexto, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        contexto = {}
    contexto.update(_build_context_payload(session, handoff_token))
    conversacion.contexto = json.dumps(contexto, ensure_ascii=False, default=str)


def get_synced_conversation(session: WebBotSesion, metadata: dict | None = None) -> WhatsAppConversacion | None:
    metadata = metadata if isinstance(metadata, dict) else _parse_metadata(session.metadata_json)
    state = _sync_state(metadata)
    conversation_id = state.get('id_whatsapp_conversacion')
    if not conversation_id:
        return None
    return db.session.get(WhatsAppConversacion, conversation_id)


def link_session_to_conversation(
    session: WebBotSesion,
    conversation_id: int,
    *,
    metadata: dict | None = None,
) -> dict:
    metadata = metadata if isinstance(metadata, dict) else _parse_metadata(session.metadata_json)
    state = _sync_state(metadata)
    state['id_whatsapp_conversacion'] = conversation_id
    metadata[SYNC_STATE_KEY] = state
    return _persist_metadata(session, metadata)


def mark_web_message_synced(
    session: WebBotSesion,
    web_message_id: int,
    *,
    metadata: dict | None = None,
    conversation_id: int | None = None,
) -> dict:
    metadata = metadata if isinstance(metadata, dict) else _parse_metadata(session.metadata_json)
    state = _sync_state(metadata)
    state['last_web_message_id'] = max(int(state.get('last_web_message_id') or 0), int(web_message_id or 0))
    if conversation_id:
        state['id_whatsapp_conversacion'] = conversation_id
    metadata[SYNC_STATE_KEY] = state
    return _persist_metadata(session, metadata)


def ensure_synced_conversation(
    session: WebBotSesion,
    *,
    metadata: dict | None = None,
    force_mode: str | None = None,
    handoff_token: str | None = None,
) -> tuple[WhatsAppConversacion, dict]:
    metadata = metadata if isinstance(metadata, dict) else _parse_metadata(session.metadata_json)
    state = _sync_state(metadata)
    conversation = None
    if state.get('id_whatsapp_conversacion'):
        conversation = db.session.get(WhatsAppConversacion, state['id_whatsapp_conversacion'])
        if conversation and not conversation.activa:
            conversation = None

    now = datetime.utcnow()
    queue_phone = _session_phone(session)
    handoff_token = (handoff_token or _pending_handoff_token(session) or '').strip()
    desired_mode = force_mode or (conversation.modo if conversation else 'bot')
    desired_name = _session_name(session, queue_phone)

    if conversation is None:
        conversation = WhatsAppConversacion(
            telefono=queue_phone,
            nombre_contacto=desired_name,
            modo=desired_mode,
            activa=True,
            inicio_sesion=now,
            ultima_actividad=now,
            contexto='{}',
        )
        db.session.add(conversation)
        db.session.flush()
    else:
        if session.telefono_visitante or str(conversation.telefono or '').startswith('WBS-'):
            conversation.telefono = queue_phone
        if desired_name:
            conversation.nombre_contacto = desired_name
        if force_mode:
            conversation.modo = force_mode
        conversation.ultima_actividad = now

    _merge_context(conversation, session, handoff_token)
    state['id_whatsapp_conversacion'] = conversation.id
    metadata[SYNC_STATE_KEY] = state
    _persist_metadata(session, metadata)
    return conversation, metadata


def sync_session_messages_to_crm(
    session: WebBotSesion,
    *,
    metadata: dict | None = None,
    force_mode: str | None = None,
    handoff_token: str | None = None,
) -> WhatsAppConversacion:
    db.session.flush()
    conversation, metadata = ensure_synced_conversation(
        session,
        metadata=metadata,
        force_mode=force_mode,
        handoff_token=handoff_token,
    )
    state = _sync_state(metadata)
    last_synced_id = int(state.get('last_web_message_id') or 0)
    mensajes = (
        session.mensajes
        .filter(WebBotMensaje.id_mensaje > last_synced_id)
        .filter(WebBotMensaje.tipo_mensaje.in_(tuple(VISIBLE_SYNC_MESSAGE_TYPES)))
        .order_by(WebBotMensaje.created_at.asc(), WebBotMensaje.id_mensaje.asc())
        .all()
    )

    newest_synced_id = last_synced_id
    for mensaje in mensajes:
        db.session.add(WhatsAppMensaje(
            id_conversacion=conversation.id,
            direccion=mensaje.direccion,
            remitente=mensaje.remitente,
            tipo_mensaje=mensaje.tipo_mensaje,
            contenido=mensaje.contenido,
            created_at=mensaje.created_at or datetime.utcnow(),
        ))
        newest_synced_id = mensaje.id_mensaje
        if mensaje.created_at:
            conversation.ultima_actividad = mensaje.created_at

    if newest_synced_id != last_synced_id:
        state['last_web_message_id'] = newest_synced_id
        metadata[SYNC_STATE_KEY] = state
        _persist_metadata(session, metadata)

    _merge_context(conversation, session, (handoff_token or _pending_handoff_token(session) or '').strip())
    return conversation
