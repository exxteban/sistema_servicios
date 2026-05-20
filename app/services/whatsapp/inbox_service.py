"""
Servicios para construir el inbox del panel de WhatsApp.
"""
import json
import re
import unicodedata

from app.models.whatsapp import (
    WhatsAppAsignacionConversacion,
    WhatsAppConversacion,
    WhatsAppMensaje,
)
from app.services.whatsapp.contexto_service import reingreso_bandeja_bloqueado


def get_conversation_origin_meta(conv: WhatsAppConversacion) -> dict:
    try:
        contexto = json.loads(conv.contexto or '{}')
        contexto = contexto if isinstance(contexto, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        contexto = {}

    web_bot = contexto.get('web_bot') if isinstance(contexto.get('web_bot'), dict) else {}
    is_store_bot = bool(web_bot.get('id_sesion_web'))

    if is_store_bot:
        return {
            'origen_tipo': 'bot_tienda',
            'origen_icono': 'fas fa-robot',
            'origen_label': web_bot.get('label') or 'Bot tienda',
            'origen_web_bot': True,
            'origen_web_label': web_bot.get('label') or 'Bot tienda',
            'origen_web_token': web_bot.get('handoff_token') or '',
        }

    return {
        'origen_tipo': 'whatsapp',
        'origen_icono': 'fab fa-whatsapp',
        'origen_label': 'WhatsApp',
        'origen_web_bot': False,
        'origen_web_label': '',
        'origen_web_token': '',
    }


def is_store_web_conversation(conv: WhatsAppConversacion) -> bool:
    try:
        contexto = json.loads(conv.contexto or '{}')
        contexto = contexto if isinstance(contexto, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    web_bot = contexto.get('web_bot') if isinstance(contexto.get('web_bot'), dict) else {}
    return bool(web_bot.get('id_sesion_web'))

def build_advisor_inbox_payload(advisor_id: int) -> dict:
    asignaciones = WhatsAppAsignacionConversacion.query.filter(
        WhatsAppAsignacionConversacion.id_asesor == advisor_id,
        WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa']),
    ).order_by(WhatsAppAsignacionConversacion.asignado_at.desc()).all()

    conversaciones = []
    for asignacion in asignaciones:
        conv = asignacion.conversacion
        if not conv:
            continue
        conversaciones.append(_serialize_assignment(conv, asignacion))

    cola = _build_queue_payload()
    return {
        'conversaciones': conversaciones,
        'cola': cola,
    }


def _build_queue_payload() -> list[dict]:
    cola = []
    convs_cola = WhatsAppConversacion.query.filter_by(
        activa=True,
        modo='derivacion',
    ).order_by(WhatsAppConversacion.ultima_actividad.desc()).limit(50).all()

    convs_bot_candidatas = WhatsAppConversacion.query.filter_by(
        activa=True,
        modo='bot',
    ).order_by(WhatsAppConversacion.ultima_actividad.desc()).limit(50).all()

    for conv in convs_cola:
        if _has_active_assignment(conv.id):
            continue
        cola.append(_serialize_queue_item(conv))

    ids_cola = {item['id_conversacion'] for item in cola}
    for conv in convs_bot_candidatas:
        if conv.id in ids_cola or not should_surface_bot_conversation_in_queue(conv) or _has_active_assignment(conv.id):
            continue
        cola.append(_serialize_queue_item(conv))

    cola.sort(key=lambda item: item.get('ultima_actividad') or '', reverse=True)
    return cola


def _serialize_assignment(conv: WhatsAppConversacion, asignacion: WhatsAppAsignacionConversacion) -> dict:
    ultimo_msg = _get_last_incoming_message(conv.id)
    return {
        'id_asignacion': asignacion.id,
        'id_conversacion': conv.id,
        'telefono': conv.telefono,
        'nombre_contacto': conv.nombre_contacto or conv.telefono,
        'estado_asignacion': asignacion.estado,
        'asignado_at': asignacion.asignado_at.isoformat() if asignacion.asignado_at else None,
        'ultimo_mensaje': ultimo_msg.contenido[:100] if ultimo_msg else '',
        'ultimo_mensaje_at': ultimo_msg.created_at.isoformat() if ultimo_msg else None,
        **get_conversation_origin_meta(conv),
    }


def _serialize_queue_item(conv: WhatsAppConversacion) -> dict:
    ultimo_msg = _get_last_incoming_message(conv.id)
    return {
        'id_conversacion': conv.id,
        'telefono': conv.telefono,
        'nombre_contacto': conv.nombre_contacto or conv.telefono,
        'estado': 'cola',
        'ultima_actividad': conv.ultima_actividad.isoformat() if conv.ultima_actividad else None,
        'ultimo_mensaje': ultimo_msg.contenido[:100] if ultimo_msg else '',
        'ultimo_mensaje_at': ultimo_msg.created_at.isoformat() if ultimo_msg else None,
        **get_conversation_origin_meta(conv),
    }


def _get_last_incoming_message(conversation_id: int) -> WhatsAppMensaje | None:
    return WhatsAppMensaje.query.filter_by(
        id_conversacion=conversation_id,
        direccion='entrante',
    ).order_by(WhatsAppMensaje.created_at.desc(), WhatsAppMensaje.id.desc()).first()


def _has_active_assignment(conversation_id: int) -> bool:
    asignacion = WhatsAppAsignacionConversacion.query.filter_by(
        id_conversacion=conversation_id,
    ).first()
    return bool(asignacion and asignacion.estado in ('pendiente', 'activa'))


def _normalize_text(texto: str) -> str:
    normalized = (texto or '').strip().lower()
    normalized = unicodedata.normalize('NFKD', normalized)
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', normalized)


def _client_confirms(texto: str) -> bool:
    normalized = _normalize_text(texto)
    if not normalized:
        return False
    if normalized in {'s', 'si', 'sí', 'ok', 'okay', 'dale', 'de una', 'claro', 'listo', 'por favor', 'confirmo'}:
        return True
    return (
        normalized.startswith('si ')
        or normalized.startswith('sí ')
        or normalized.startswith('ok ')
        or normalized.startswith('dale ')
    )


def _bot_offered_handoff(texto: str) -> bool:
    normalized = _normalize_text(texto)
    return (
        'queres que te comunique con un asesor' in normalized
        or 'queres hablar con un asesor' in normalized
        or 'queres hablar con alguien' in normalized
        or 'te comunique con un asesor' in normalized
    )


def _is_handoff_confirmation(conv: WhatsAppConversacion) -> bool:
    mensajes = WhatsAppMensaje.query.filter_by(
        id_conversacion=conv.id,
    ).order_by(WhatsAppMensaje.created_at.desc(), WhatsAppMensaje.id.desc()).limit(6).all()

    if not mensajes:
        return False

    ultimo = mensajes[0]
    if ultimo.direccion != 'entrante' or ultimo.remitente != 'cliente':
        return False
    if not _client_confirms(ultimo.contenido or ''):
        return False

    return any(
        mensaje.direccion == 'saliente'
        and mensaje.remitente == 'bot'
        and _bot_offered_handoff(mensaje.contenido or '')
        for mensaje in mensajes[1:]
    )


def should_surface_bot_conversation_in_queue(conv: WhatsAppConversacion) -> bool:
    if not conv or conv.modo != 'bot':
        return False
    if reingreso_bandeja_bloqueado(conv):
        return False
    return _is_handoff_confirmation(conv)
