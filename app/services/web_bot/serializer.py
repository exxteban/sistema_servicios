"""
Serialización del bot web para la API pública.
"""
import json

from app.models.web_bot import WebBotMensaje


VISIBLE_MESSAGE_TYPES = {'text', 'note'}


def build_bot_config(config) -> dict:
    store_name = config.nombre_tienda or 'la tienda'
    return {
        'assistant_name': 'Asistente IA',
        'assistant_badge': 'Asistente IA',
        'greeting': (
            f'Hola, soy el Asistente IA de {store_name}. '
            'Antes de seguir, pasame tu número de teléfono para identificarte y que un asesor pueda continuar la atención si hace falta.'
        ),
        'disclaimer': 'Las respuestas se basan en el catálogo y la configuración pública de la tienda.',
        'color': config.color_primario or '#2563eb',
        'avatar_label': 'IA',
        'widget_enabled': True,
        'standalone_enabled': True,
        'whatsapp_phone': config.telefono_whatsapp or '',
    }


def parse_metadata(raw_value: str | None) -> dict:
    try:
        data = json.loads(raw_value or '{}')
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def serialize_message(message, include_hidden: bool = False) -> dict | None:
    if not include_hidden and message.tipo_mensaje not in VISIBLE_MESSAGE_TYPES:
        return None
    return {
        'id': message.id_mensaje,
        'direccion': message.direccion,
        'remitente': message.remitente,
        'tipo_mensaje': message.tipo_mensaje,
        'contenido': message.contenido,
        'created_at': message.created_at.isoformat() if message.created_at else None,
    }


def serialize_session(session, bot_config: dict, include_hidden: bool = False) -> dict:
    historial = []
    messages = session.mensajes.order_by(WebBotMensaje.created_at.asc(), WebBotMensaje.id_mensaje.asc()).all()
    for message in messages:
        item = serialize_message(message, include_hidden=include_hidden)
        if item:
            historial.append(item)
    return {
        'session_token': session.session_token,
        'estado': session.estado,
        'origen': session.origen,
        'historial': historial,
        'bot': bot_config,
        'metadata': parse_metadata(session.metadata_json),
    }
