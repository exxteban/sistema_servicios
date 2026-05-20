"""
Helpers para leer/escribir banderas del contexto de conversaciones WhatsApp.
"""
from __future__ import annotations

import json
from datetime import datetime

from app.models.whatsapp import WhatsAppConversacion


_INBOX_BLOCK_KEY = 'bloqueo_reingreso_bandeja'


def cargar_contexto(conv: WhatsAppConversacion | None) -> dict:
    if not conv or not conv.contexto:
        return {}
    try:
        contexto = json.loads(conv.contexto)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return contexto if isinstance(contexto, dict) else {}


def guardar_contexto(conv: WhatsAppConversacion | None, contexto: dict):
    if not conv:
        return
    conv.contexto = json.dumps(contexto or {}, ensure_ascii=False, default=str)


def bloquear_reingreso_bandeja(
    conv: WhatsAppConversacion | None,
    motivo: str,
    *,
    ahora: datetime | None = None,
):
    if not conv:
        return
    contexto = cargar_contexto(conv)
    contexto[_INBOX_BLOCK_KEY] = {
        'activo': True,
        'motivo': (motivo or '').strip() or 'manual',
        'at': (ahora or datetime.utcnow()).isoformat(),
    }
    guardar_contexto(conv, contexto)


def limpiar_bloqueo_reingreso_bandeja(conv: WhatsAppConversacion | None):
    if not conv:
        return
    contexto = cargar_contexto(conv)
    if contexto.pop(_INBOX_BLOCK_KEY, None) is None:
        return
    guardar_contexto(conv, contexto)


def reingreso_bandeja_bloqueado(conv: WhatsAppConversacion | None) -> bool:
    contexto = cargar_contexto(conv)
    bloqueo = contexto.get(_INBOX_BLOCK_KEY)
    return bool(isinstance(bloqueo, dict) and bloqueo.get('activo'))
