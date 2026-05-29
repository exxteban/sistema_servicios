"""Construccion consistente de URLs publicas para compartir con clientes."""
from __future__ import annotations

import os
from urllib.parse import urljoin

from flask import request, url_for

from app.models import Configuracion


CLAVE_URL_PUBLICA_SISTEMA = 'url_publica_sistema'
DESC_URL_PUBLICA_SISTEMA = 'URL publica base usada en links compartidos por WhatsApp, QR y seguimiento'


def build_public_url(endpoint: str, **values) -> str:
    """Genera una URL absoluta priorizando dominio publico configurado."""
    values.pop('_external', None)
    path = url_for(endpoint, **values)
    base_url = _public_base_url()
    if base_url:
        return urljoin(f'{base_url}/', path.lstrip('/'))
    return url_for(endpoint, _external=True, **values)


def public_base_url_configured() -> str:
    return _clean_base_url(
        Configuracion.obtener(CLAVE_URL_PUBLICA_SISTEMA, '')
        or os.environ.get('APP_PUBLIC_URL')
        or os.environ.get('PUBLIC_BASE_URL')
        or ''
    )


def _public_base_url() -> str:
    configured = public_base_url_configured()
    if configured:
        return configured

    forwarded_host = (request.headers.get('X-Forwarded-Host') or '').split(',')[0].strip()
    if forwarded_host:
        proto = (request.headers.get('X-Forwarded-Proto') or request.scheme or 'https').split(',')[0].strip()
        return _clean_base_url(f'{proto}://{forwarded_host}')

    return ''


def _clean_base_url(value: str) -> str:
    url = (value or '').strip().strip('"\'`')
    if not url:
        return ''
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    return url.rstrip('/')
