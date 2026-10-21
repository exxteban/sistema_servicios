"""Totales de IVA que un documento electrónico le declaró a SIFEN.

Para el resumen de la contadora el IVA de una venta sale del XML (`gTotSub`)
y no de `Venta.total_iva_10`: ese campo se calcula antes del descuento y del
redondeo, y la contadora compara contra lo que figura en Marangatu, que es lo
que dice el XML.
"""
import xml.etree.ElementTree as ET
from math import isfinite

from facturacion_electronica.services.receptor_facturado import NS_SIFEN

# Exento y exonerado van juntos: ninguno lleva IVA.
CAMPOS = {
    'exenta': ('dSubExe', 'dSubExo'),
    'base5': ('dBaseGrav5',),
    'iva5': ('dIVA5',),
    'base10': ('dBaseGrav10',),
    'iva10': ('dIVA10',),
    'total': ('dTotGralOpe',),
}


def _numero(nodo):
    try:
        valor = float(nodo.text.strip())
        return valor if isfinite(valor) else None
    except (AttributeError, ValueError):
        return None


def totales_declarados(xml):
    """{exenta, base5, iva5, base10, iva10, total} del XML, o None si no se puede leer."""
    if not xml:
        return None
    try:
        raiz = ET.fromstring(xml.encode('utf-8') if isinstance(xml, str) else xml)
    except (ET.ParseError, ValueError):
        return None
    sub = raiz.find(f'.//{NS_SIFEN}gTotSub')
    prefijo = NS_SIFEN
    if sub is None:
        sub = raiz.find('.//gTotSub')
        prefijo = ''
    if sub is None:
        return None
    if sub.find(f'{prefijo}dTotGralOpe') is None:
        return None
    totales = {}
    for clave, tags in CAMPOS.items():
        valores = [_numero(sub.find(f'{prefijo}{tag}')) for tag in tags
                   if sub.find(f'{prefijo}{tag}') is not None]
        if any(valor is None for valor in valores):
            return None
        totales[clave] = sum(valores)
    return totales
