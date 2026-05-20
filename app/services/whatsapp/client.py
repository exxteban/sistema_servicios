"""
Cliente HTTP para WhatsApp Cloud API (Graph API v21.0).
Enviar mensajes de texto, interactivos (botones/listas) y templates.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = 'v21.0'
GRAPH_API_BASE = f'https://graph.facebook.com/{GRAPH_API_VERSION}'


def _get_config():
    """Obtiene configuracion de WhatsApp desde variables de entorno."""
    return {
        'phone_number_id': os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '') or os.environ.get('WHATSAPP_PHONE_ID', ''),
        'access_token': os.environ.get('WHATSAPP_ACCESS_TOKEN', '') or os.environ.get('WHATSAPP_TOKEN', ''),
        'dry_run': os.environ.get('WHATSAPP_DRY_RUN', '0').strip().lower() in ('1', 'true', 'yes'),
    }


def _headers():
    cfg = _get_config()
    return {
        'Authorization': f'Bearer {cfg["access_token"]}',
        'Content-Type': 'application/json',
    }


def _messages_url():
    cfg = _get_config()
    return f'{GRAPH_API_BASE}/{cfg["phone_number_id"]}/messages'


def enviar_texto(telefono: str, texto: str) -> dict | None:
    """
    Envia un mensaje de texto simple.
    telefono: formato internacional sin + (ej: '595981123456')
    """
    cfg = _get_config()
    if cfg['dry_run']:
        logger.info(f"[DRY_RUN] Enviar texto a {telefono}: {texto[:100]}")
        return {'dry_run': True, 'to': telefono}

    payload = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': telefono,
        'type': 'text',
        'text': {'body': texto}
    }

    try:
        resp = requests.post(_messages_url(), json=payload, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Mensaje enviado a {telefono}: {data}")
        return data
    except requests.RequestException as e:
        status_code = None
        response_text = None
        try:
            if getattr(e, "response", None) is not None:
                status_code = getattr(e.response, "status_code", None)
                response_text = getattr(e.response, "text", None)
        except Exception:
            pass
        if status_code is not None:
            logger.error(f"Error enviando mensaje a {telefono}: {e} (HTTP {status_code}) resp={response_text}")
        else:
            logger.error(f"Error enviando mensaje a {telefono}: {e}")
        return None


def enviar_botones(telefono: str, texto_body: str, botones: list[dict]) -> dict | None:
    """
    Envia mensaje interactivo con botones (max 3).
    botones: [{"id": "btn_1", "title": "Opcion 1"}, ...]
    """
    cfg = _get_config()
    if cfg['dry_run']:
        logger.info(f"[DRY_RUN] Enviar botones a {telefono}: {texto_body[:80]}")
        return {'dry_run': True, 'to': telefono}

    rows = [{'type': 'reply', 'reply': {'id': b['id'], 'title': b['title'][:20]}} for b in botones[:3]]

    payload = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': telefono,
        'type': 'interactive',
        'interactive': {
            'type': 'button',
            'body': {'text': texto_body},
            'action': {'buttons': rows}
        }
    }

    try:
        resp = requests.post(_messages_url(), json=payload, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Botones enviados a {telefono}: {data}")
        return data
    except requests.RequestException as e:
        status_code = None
        response_text = None
        try:
            if getattr(e, "response", None) is not None:
                status_code = getattr(e.response, "status_code", None)
                response_text = getattr(e.response, "text", None)
        except Exception:
            pass
        if status_code is not None:
            logger.error(f"Error enviando botones a {telefono}: {e} (HTTP {status_code}) resp={response_text}")
        else:
            logger.error(f"Error enviando botones a {telefono}: {e}")
        return None


def enviar_lista(telefono: str, texto_body: str, boton_texto: str, secciones: list[dict]) -> dict | None:
    """
    Envia mensaje interactivo con lista.
    secciones: [{"title": "Seccion", "rows": [{"id": "r1", "title": "Item", "description": "..."}]}]
    """
    cfg = _get_config()
    if cfg['dry_run']:
        logger.info(f"[DRY_RUN] Enviar lista a {telefono}: {texto_body[:80]}")
        return {'dry_run': True, 'to': telefono}

    payload = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': telefono,
        'type': 'interactive',
        'interactive': {
            'type': 'list',
            'body': {'text': texto_body},
            'action': {
                'button': boton_texto[:20],
                'sections': secciones
            }
        }
    }

    try:
        resp = requests.post(_messages_url(), json=payload, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Lista enviada a {telefono}: {data}")
        return data
    except requests.RequestException as e:
        status_code = None
        response_text = None
        try:
            if getattr(e, "response", None) is not None:
                status_code = getattr(e.response, "status_code", None)
                response_text = getattr(e.response, "text", None)
        except Exception:
            pass
        if status_code is not None:
            logger.error(f"Error enviando lista a {telefono}: {e} (HTTP {status_code}) resp={response_text}")
        else:
            logger.error(f"Error enviando lista a {telefono}: {e}")
        return None


def enviar_template(telefono: str, nombre_template: str, idioma: str = 'es',
                    componentes: list | None = None) -> dict | None:
    """Envia un mensaje de template aprobado por Meta."""
    cfg = _get_config()
    if cfg['dry_run']:
        logger.info(f"[DRY_RUN] Enviar template '{nombre_template}' a {telefono}")
        return {'dry_run': True, 'to': telefono}

    template_obj = {
        'name': nombre_template,
        'language': {'code': idioma}
    }
    if componentes:
        template_obj['components'] = componentes

    payload = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': telefono,
        'type': 'template',
        'template': template_obj
    }

    try:
        resp = requests.post(_messages_url(), json=payload, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Template enviado a {telefono}: {data}")
        return data
    except requests.RequestException as e:
        status_code = None
        response_text = None
        try:
            if getattr(e, "response", None) is not None:
                status_code = getattr(e.response, "status_code", None)
                response_text = getattr(e.response, "text", None)
        except Exception:
            pass
        if status_code is not None:
            logger.error(f"Error enviando template a {telefono}: {e} (HTTP {status_code}) resp={response_text}")
        else:
            logger.error(f"Error enviando template a {telefono}: {e}")
        return None


def marcar_leido(wa_message_id: str) -> bool:
    """Marca un mensaje como leido (double blue check)."""
    cfg = _get_config()
    if cfg['dry_run']:
        return True

    payload = {
        'messaging_product': 'whatsapp',
        'status': 'read',
        'message_id': wa_message_id
    }

    try:
        resp = requests.post(_messages_url(), json=payload, headers=_headers(), timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        status_code = None
        response_text = None
        try:
            if getattr(e, "response", None) is not None:
                status_code = getattr(e.response, "status_code", None)
                response_text = getattr(e.response, "text", None)
        except Exception:
            pass
        if status_code is not None:
            logger.warning(f"Error marcando leido {wa_message_id}: {e} (HTTP {status_code}) resp={response_text}")
        else:
            logger.warning(f"Error marcando leido {wa_message_id}: {e}")
        return False


def obtener_media_info(media_id: str) -> dict | None:
    cfg = _get_config()
    if cfg['dry_run']:
        return {'dry_run': True, 'id': media_id}

    if not media_id:
        return None

    url = f'{GRAPH_API_BASE}/{media_id}'
    try:
        resp = requests.get(
            url,
            params={'fields': 'url,mime_type,sha256,file_size'},
            headers={'Authorization': f'Bearer {cfg["access_token"]}'},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        status_code = None
        response_text = None
        try:
            if getattr(e, "response", None) is not None:
                status_code = getattr(e.response, "status_code", None)
                response_text = getattr(e.response, "text", None)
        except Exception:
            pass
        if status_code is not None:
            logger.error(f"Error obteniendo media info {media_id}: {e} (HTTP {status_code}) resp={response_text}")
        else:
            logger.error(f"Error obteniendo media info {media_id}: {e}")
        return None


def descargar_media(media_id: str) -> tuple[bytes, dict] | None:
    cfg = _get_config()
    if cfg['dry_run']:
        return b'', {'dry_run': True, 'id': media_id}

    info = obtener_media_info(media_id)
    if not info:
        return None

    media_url = info.get('url')
    if not media_url:
        return None

    try:
        resp = requests.get(
            media_url,
            headers={'Authorization': f'Bearer {cfg["access_token"]}'},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.content, info
    except requests.RequestException as e:
        status_code = None
        response_text = None
        try:
            if getattr(e, "response", None) is not None:
                status_code = getattr(e.response, "status_code", None)
                response_text = getattr(e.response, "text", None)
        except Exception:
            pass
        if status_code is not None:
            logger.error(f"Error descargando media {media_id}: {e} (HTTP {status_code}) resp={response_text}")
        else:
            logger.error(f"Error descargando media {media_id}: {e}")
        return None
