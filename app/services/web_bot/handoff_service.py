"""
Generación y consumo de handoff entre bot web y WhatsApp.
"""
import json
import re
import secrets
from datetime import datetime

from app import db
from app.models.web_bot import WebBotHandoff, WebBotMensaje, WebBotSesion
from app.models.whatsapp import WhatsAppConversacion
from app.services.web_bot.crm_sync_service import (
    get_synced_conversation,
    link_session_to_conversation,
    mark_web_message_synced,
    sync_session_messages_to_crm,
)
from app.services.whatsapp.auditoria_service import registrar_evento_conversacion
from app.utils.phone_utils import formatear_telefono_display, normalizar_telefono


HANDOFF_TOKEN_RE = re.compile(r'\b(WBH-[A-Z0-9]{6,12})\b', re.IGNORECASE)


def _build_handoff_token() -> str:
    return f"WBH-{secrets.token_hex(4).upper()}"


def _normalize_phone(phone: str | None) -> str:
    return ''.join(ch for ch in str(phone or '') if ch.isdigit())


def _serialize_whatsapp_origin(session, handoff) -> dict:
    return {
        'origen': session.origen or 'tienda_widget',
        'canal_origen': 'web',
        'label': 'Bot tienda',
        'handoff_token': handoff.handoff_token,
        'id_sesion_web': session.id_sesion,
        'slug_tienda': session.slug_tienda,
        'fecha_handoff': handoff.created_at.isoformat() if handoff.created_at else None,
    }


def _get_text_messages(session, max_messages: int = 100) -> list[WebBotMensaje]:
    mensajes = (
        session.mensajes
        .filter_by(tipo_mensaje='text')
        .order_by(WebBotMensaje.created_at.asc(), WebBotMensaje.id_mensaje.asc())
        .all()
    )
    if len(mensajes) > max(1, max_messages):
        return mensajes[-max_messages:]
    return mensajes


def _web_message_preview(session, max_messages: int = 100) -> list[dict]:
    mensajes = _get_text_messages(session, max_messages=max_messages)
    preview = []
    for msg in mensajes:
        if not (msg.contenido or '').strip():
            continue
        preview.append({
            'direccion': msg.direccion,
            'remitente': msg.remitente,
            'contenido': (msg.contenido or '')[:500],
            'created_at': msg.created_at.isoformat() if msg.created_at else None,
        })
    return preview


def _build_web_queue_phone(handoff_token: str) -> str:
    return (handoff_token or 'WBH').strip().upper()[:20]


def _resolve_queue_phone(session, handoff) -> str:
    telefono = normalizar_telefono(session.telefono_visitante or '')
    if telefono:
        return telefono
    return _build_web_queue_phone(handoff.handoff_token)


def _build_queue_contact_name(session, queue_phone: str) -> str:
    nombre = (session.nombre_visitante or '').strip()
    if nombre:
        return nombre

    telefono_visitante = normalizar_telefono(session.telefono_visitante or '') or queue_phone
    if telefono_visitante and not str(telefono_visitante).startswith('WBH-'):
        return f'Web {formatear_telefono_display(telefono_visitante)}'

    return f'Bot Web {session.slug_tienda}'


def _build_interest_summary(session, limit: int = 3) -> str:
    mensajes = (
        session.mensajes
        .filter_by(direccion='entrante', tipo_mensaje='text')
        .order_by(WebBotMensaje.created_at.desc(), WebBotMensaje.id_mensaje.desc())
        .limit(max(1, min(limit, 6)))
        .all()
    )
    partes = []
    for msg in reversed(mensajes):
        contenido = (msg.contenido or '').strip()
        if not contenido:
            continue
        partes.append(contenido[:180])
    return ' | '.join(partes)


def _get_pending_handoff(session) -> WebBotHandoff | None:
    if not session:
        return None
    return session.handoffs.filter_by(estado='generado').first()


def ensure_handoff_whatsapp(session, config, motivo: str) -> tuple[WebBotHandoff, bool]:
    handoff = _get_pending_handoff(session)
    if handoff:
        if handoff.id_whatsapp_conversacion:
            conv = db.session.get(WhatsAppConversacion, handoff.id_whatsapp_conversacion)
            if conv and conv.activa:
                sync_session_messages_to_crm(
                    session,
                    force_mode='derivacion',
                    handoff_token=handoff.handoff_token,
                )
                session.estado = 'handoff'
                session.ultima_actividad = datetime.utcnow()
                return handoff, False
        conv = encolar_handoff_en_whatsapp(session, handoff)
        session.estado = 'handoff'
        session.ultima_actividad = datetime.utcnow()
        handoff.id_whatsapp_conversacion = conv.id
        return handoff, False

    handoff = crear_handoff_whatsapp(session, config, motivo)
    conv = encolar_handoff_en_whatsapp(session, handoff)
    handoff.id_whatsapp_conversacion = conv.id
    return handoff, True


def encolar_handoff_en_whatsapp(session, handoff) -> WhatsAppConversacion:
    conv = sync_session_messages_to_crm(
        session,
        force_mode='derivacion',
        handoff_token=handoff.handoff_token,
    )
    queue_phone = _resolve_queue_phone(session, handoff)
    conv.telefono = queue_phone
    conv.nombre_contacto = _build_queue_contact_name(session, queue_phone)
    handoff.id_whatsapp_conversacion = conv.id
    registrar_evento_conversacion(conv, 'handoff_web_creado', detalle=_serialize_whatsapp_origin(session, handoff))
    return conv


def obtener_handoff_web_pendiente_por_conversacion(conversacion) -> WebBotHandoff | None:
    if not conversacion:
        return None
    return WebBotHandoff.query.filter_by(
        id_whatsapp_conversacion=conversacion.id,
        estado='generado',
    ).first()


def registrar_mensaje_cliente_desde_web(session, contenido: str):
    handoff = session.handoffs.filter_by(estado='generado').first()
    conv = get_synced_conversation(session)
    if not conv or not conv.activa:
        return None
    if not handoff and conv.modo not in {'derivacion', 'asesor'} and session.estado not in {'handoff', 'asesor'}:
        return None
    now = datetime.utcnow()
    conv.ultima_actividad = now
    session.estado = 'asesor' if conv.modo == 'asesor' else 'handoff'
    session.ultima_actividad = now
    return conv


def registrar_respuesta_asesor_en_web(conversacion, texto: str) -> bool:
    try:
        contexto = json.loads(conversacion.contexto or '{}')
        contexto = contexto if isinstance(contexto, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        contexto = {}

    web_bot = contexto.get('web_bot') if isinstance(contexto.get('web_bot'), dict) else {}
    session_id = web_bot.get('id_sesion_web')
    if not session_id:
        return False

    session = db.session.get(WebBotSesion, session_id)
    if not session:
        return False

    now = datetime.utcnow()
    session.estado = 'asesor'
    session.ultima_actividad = now
    mensaje = WebBotMensaje(
        id_sesion=session.id_sesion,
        direccion='saliente',
        remitente='asesor',
        tipo_mensaje='text',
        contenido=texto,
        created_at=now,
    )
    db.session.add(mensaje)
    db.session.flush()
    mark_web_message_synced(session, mensaje.id_mensaje, conversation_id=conversacion.id)
    return True


def crear_handoff_whatsapp(session, config, motivo: str) -> WebBotHandoff:
    handoff = WebBotHandoff(
        id_sesion=session.id_sesion,
        handoff_token=_build_handoff_token(),
        canal_destino='whatsapp',
        estado='generado',
        telefono_destino=config.telefono_whatsapp,
    )
    prefill = (
        f'Hola, vengo del bot de {config.nombre_tienda or "la tienda"} y necesito pasar a la cola de atención. '
        f'Código: {handoff.handoff_token}'
    )
    handoff.texto_prefill = prefill
    session.estado = 'handoff'
    session.ultimo_handoff_token = handoff.handoff_token
    session.ultima_actividad = datetime.utcnow()
    try:
        metadata = json.loads(session.metadata_json or '{}')
        metadata = metadata if isinstance(metadata, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        metadata = {}
    metadata['ultimo_handoff'] = {
        'motivo': motivo,
        'handoff_token': handoff.handoff_token,
        'created_at': datetime.utcnow().isoformat(),
    }
    session.metadata_json = json.dumps(metadata, ensure_ascii=False, default=str)
    db.session.add(handoff)
    db.session.flush()
    return handoff


def build_whatsapp_url(phone: str | None, texto_prefill: str) -> str:
    normalized_phone = _normalize_phone(phone)
    if not normalized_phone:
        return ''
    from urllib.parse import quote
    return f'https://wa.me/{normalized_phone}?text={quote(texto_prefill)}'


def consumir_handoff_desde_whatsapp(conversacion, texto: str) -> dict | None:
    match = HANDOFF_TOKEN_RE.search(texto or '')
    if not match:
        return None

    handoff = WebBotHandoff.query.filter_by(handoff_token=match.group(1).upper()).first()
    if not handoff or handoff.estado not in {'generado', 'usado'}:
        return None

    session = handoff.sesion
    if not session:
        return None

    old_conv_id = handoff.id_whatsapp_conversacion
    handoff.estado = 'usado'
    handoff.used_at = handoff.used_at or datetime.utcnow()
    handoff.id_whatsapp_conversacion = conversacion.id
    session.estado = 'handoff'
    session.ultima_actividad = datetime.utcnow()

    try:
        contexto = json.loads(conversacion.contexto or '{}')
        contexto = contexto if isinstance(contexto, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        contexto = {}
    contexto['web_bot'] = _serialize_whatsapp_origin(session, handoff)
    conversacion.contexto = json.dumps(contexto, ensure_ascii=False, default=str)
    conversacion.modo = 'derivacion'

    if old_conv_id and old_conv_id != conversacion.id:
        old_conv = db.session.get(WhatsAppConversacion, old_conv_id)
        if old_conv and old_conv.activa:
            old_conv.activa = False
            old_conv.fin_sesion = datetime.utcnow()
    link_session_to_conversation(session, conversacion.id)

    return contexto['web_bot']
