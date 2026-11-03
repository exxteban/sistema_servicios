"""Mensajes de la cola de envio asistido por segmento y contexto del negocio (BI-02).

Variables: {nombre}, {plato}, {negocio}, {link}. Son solo texto: el sistema no envia nada.
"""
from __future__ import annotations

import re

from app import db
from app.models import Cliente
from app.models.tienda import TiendaConfig
from app.utils.public_url import build_public_url

PLANTILLAS_DEFAULT = {
    'habitual_ausente': 'Hola {nombre}, hace tiempo que no pedís en {negocio}. ¿Te antojás de {plato}? Pedí acá: {link}',
    'segunda_compra': 'Hola {nombre}, gracias por tu pedido en {negocio}. ¿Qué tal te quedó {plato}? Si querés volver a pedir: {link}',
}
PLATO_SIN_DATO = {
    'habitual_ausente': 'algo rico de la casa',
    'segunda_compra': 'tu pedido',
}
_VARIABLE = re.compile(r'\{(nombre|plato|negocio|link)\}')
_LINK_SIN_TIENDA = re.compile(r'\s*:?\s*\{link\}')


def contexto_negocio(cliente_id: int) -> dict:
    cliente = db.session.get(Cliente, int(cliente_id))
    tienda = TiendaConfig.query.filter_by(id_cliente=int(cliente_id)).first()
    negocio = ((tienda.nombre_tienda if tienda else '') or (cliente.nombre if cliente else '') or '').strip()
    return {'negocio': negocio, 'link': _link_tienda(tienda)}


def _link_tienda(tienda: TiendaConfig | None) -> str:
    if not tienda or not tienda.activa or not tienda.slug:
        return ''
    try:
        return build_public_url('tienda_public.tienda_spa', slug=tienda.slug)
    except RuntimeError:
        return ''


def renderizar(segmento: str, texto: str | None, *, nombre: str, plato: str | None, negocio: str, link: str) -> str:
    base = (texto or '').strip() or PLANTILLAS_DEFAULT[segmento]
    if not link:
        base = _LINK_SIN_TIENDA.sub('', base)
    valores = {
        'nombre': (nombre or '').strip() or 'amigo',
        'plato': (plato or '').strip() or PLATO_SIN_DATO[segmento],
        'negocio': (negocio or '').strip() or 'nuestro local',
        'link': link,
    }
    salida = _VARIABLE.sub(lambda match: valores[match.group(1)], base)
    return ' '.join(salida.split())
