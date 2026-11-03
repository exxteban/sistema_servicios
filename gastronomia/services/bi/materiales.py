"""Materiales de activacion comercial: QR, texto para la bio y texto para el estado de WhatsApp (BI-04).

Solo generan texto y un SVG para que el dueno los copie o descargue. El sistema no publica nada.
Sin tienda activa o sin URL publica no hay materiales, para no mostrar un enlace roto.
"""
from __future__ import annotations

import base64

from app.utils.seguimiento_utils import generar_qr_svg
from gastronomia.services.bi.plantillas import contexto_negocio

TEXTO_BIO = 'Pedí online en {negocio}: {link}'
TEXTO_ESTADO = '¡Ya podés pedir en nuestra tienda online, sin esperar! {link}'
NEGOCIO_SIN_NOMBRE = 'nuestro local'


def materiales_activacion(cliente_id: int) -> dict | None:
    contexto = contexto_negocio(cliente_id)
    link = contexto['link']
    if not link:
        return None
    negocio = contexto['negocio'] or NEGOCIO_SIN_NOMBRE
    qr_svg = _qr_svg(link)
    return {
        'link': link,
        'bio': TEXTO_BIO.format(negocio=negocio, link=link),
        'estado_whatsapp': TEXTO_ESTADO.format(link=link),
        'qr_svg': qr_svg,
        'qr_descarga': _data_uri_svg(qr_svg) if qr_svg else '',
    }


def _qr_svg(link: str) -> str:
    try:
        return generar_qr_svg(link)
    except ImportError:
        return ''


def _data_uri_svg(svg: str) -> str:
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode('utf-8')).decode('ascii')
