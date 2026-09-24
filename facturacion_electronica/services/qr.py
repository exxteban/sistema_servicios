"""Extrae la URL del QR del XML (nodo gCamFuFD/dCarQR) y la renderiza.

El QR lo calcula el servicio Node (TIPS qrgen) con el hash del CSC; acá sólo
leemos el resultado y lo convertimos en imagen para el KuDE.
"""
import re
from html import unescape

import segno

_QR_RE = re.compile(r'<dCarQR>(.*?)</dCarQR>', re.DOTALL)


def extraer_qr_url(xml_con_qr):
    if not xml_con_qr:
        return None
    match = _QR_RE.search(xml_con_qr)
    return unescape(match.group(1).strip()) if match else None


def qr_png_data_uri(url, scale=4, border=2):
    """Devuelve la URL del QR como data URI PNG, lista para un <img>."""
    if not url:
        return None
    return segno.make(url, error='m').png_data_uri(scale=scale, border=border)


__all__ = ['extraer_qr_url', 'qr_png_data_uri']
