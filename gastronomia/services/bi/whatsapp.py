"""Enlaces wa.me con texto precargado: el mensaje lo envia el dueno desde su WhatsApp.

No se usa la WhatsApp Cloud API. Abrir el enlace no marca nada como enviado.
"""
from __future__ import annotations

from urllib.parse import quote


def url_wa_me(telefono: str | None, texto: str) -> str | None:
    digits = ''.join(ch for ch in str(telefono or '') if ch.isdigit())
    if not digits:
        return None
    return f'https://wa.me/{digits}?text={quote(texto)}'
