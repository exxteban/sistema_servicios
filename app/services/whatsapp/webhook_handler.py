"""
Procesador de webhooks entrantes de WhatsApp Cloud API.
Parsea la estructura del webhook y delega al conversacion_manager.
"""
import logging

from app.utils.phone_utils import extraer_telefono_whatsapp

logger = logging.getLogger(__name__)


def procesar_webhook(payload: dict) -> dict:
    """
    Procesa el payload completo del webhook de WhatsApp.
    Retorna dict con resultado del procesamiento.
    
    Estructura del webhook de Meta:
    {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "...", "phone_number_id": "..."},
                    "contacts": [{"profile": {"name": "..."}, "wa_id": "595981..."}],
                    "messages": [{
                        "from": "595981...",
                        "id": "wamid.xxx",
                        "timestamp": "...",
                        "type": "text",
                        "text": {"body": "hola"}
                    }],
                    "statuses": [...]
                },
                "field": "messages"
            }]
        }]
    }
    """
    resultados = []

    if payload.get('object') != 'whatsapp_business_account':
        logger.warning(f"Webhook con object inesperado: {payload.get('object')}")
        return {'procesados': 0, 'resultados': []}

    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            field = change.get('field', '')

            if field != 'messages':
                continue

            # Procesar mensajes entrantes
            messages = value.get('messages', [])
            contacts = value.get('contacts', [])

            for msg in messages:
                resultado = _procesar_mensaje(msg, contacts)
                if resultado:
                    resultados.append(resultado)

            # Procesar status updates (sent, delivered, read)
            statuses = value.get('statuses', [])
            for status in statuses:
                _procesar_status(status)

    return {'procesados': len(resultados), 'resultados': resultados}


def _procesar_mensaje(msg: dict, contacts: list) -> dict | None:
    """Procesa un mensaje individual del webhook."""
    from app.services.whatsapp.conversacion_manager import procesar_mensaje_entrante

    wa_id = msg.get('from', '')
    wa_message_id = msg.get('id', '')
    tipo = msg.get('type', 'text')

    telefono = extraer_telefono_whatsapp(wa_id)
    if not telefono:
        logger.warning(f"Mensaje sin telefono valido: {msg}")
        return None

    # Obtener nombre del contacto
    nombre = None
    for contact in contacts:
        if contact.get('wa_id') == wa_id:
            nombre = contact.get('profile', {}).get('name')
            break

    # Extraer texto segun tipo de mensaje
    texto = _extraer_texto(msg, tipo)
    if not texto:
        logger.info(f"Mensaje sin texto procesable: tipo={tipo} from={wa_id}")
        # Para tipos no soportados, enviar mensaje generico
        texto = f'[{tipo}]'

    media_id, media_mime_type = _extraer_media(msg, tipo)

    logger.info(
        "Mensaje entrante: tel=%s tipo=%s texto=%s media_id=%s",
        telefono,
        tipo,
        texto[:100],
        media_id or '',
    )

    try:
        respuesta = procesar_mensaje_entrante(
            telefono=telefono,
            texto=texto,
            nombre_contacto=nombre,
            wa_message_id=wa_message_id,
            tipo_mensaje=tipo,
            media_id=media_id,
            media_mime_type=media_mime_type,
        )
        return {
            'telefono': telefono,
            'tipo': tipo,
            'respuesta': respuesta is not None
        }
    except Exception as e:
        logger.error(f"Error procesando mensaje de {telefono}: {e}", exc_info=True)
        return None


def _extraer_texto(msg: dict, tipo: str) -> str:
    """Extrae el texto del mensaje segun su tipo."""
    if tipo == 'text':
        return msg.get('text', {}).get('body', '')

    if tipo == 'interactive':
        interactive = msg.get('interactive', {})
        int_type = interactive.get('type', '')
        if int_type == 'button_reply':
            return interactive.get('button_reply', {}).get('title', '')
        if int_type == 'list_reply':
            return interactive.get('list_reply', {}).get('title', '')

    if tipo == 'button':
        return msg.get('button', {}).get('text', '')

    if tipo == 'image':
        return msg.get('image', {}).get('caption', '[Imagen]')

    if tipo == 'document':
        return msg.get('document', {}).get('caption', '[Documento]')

    if tipo == 'audio':
        return '[Audio]'

    if tipo == 'video':
        return msg.get('video', {}).get('caption', '[Video]')

    if tipo == 'location':
        loc = msg.get('location', {})
        return f'[Ubicacion: {loc.get("latitude", "")}, {loc.get("longitude", "")}]'

    if tipo == 'contacts':
        return '[Contacto]'

    if tipo == 'sticker':
        return '[Sticker]'

    return ''


def _extraer_media(msg: dict, tipo: str) -> tuple[str | None, str | None]:
    if tipo == 'image':
        obj = msg.get('image', {}) or {}
        return (obj.get('id') or None), (obj.get('mime_type') or None)
    if tipo == 'document':
        obj = msg.get('document', {}) or {}
        return (obj.get('id') or None), (obj.get('mime_type') or None)
    if tipo == 'video':
        obj = msg.get('video', {}) or {}
        return (obj.get('id') or None), (obj.get('mime_type') or None)
    if tipo == 'audio':
        obj = msg.get('audio', {}) or {}
        return (obj.get('id') or None), (obj.get('mime_type') or None)
    return None, None


def _procesar_status(status: dict):
    """Procesa una actualizacion de status (sent, delivered, read)."""
    from app.models.whatsapp import WhatsAppMensaje
    from app import db

    wa_message_id = status.get('id', '')
    new_status = status.get('status', '')

    if not wa_message_id or not new_status:
        return

    msg = WhatsAppMensaje.query.filter_by(wa_message_id=wa_message_id).first()
    if msg:
        msg.wa_status = new_status
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
