"""Acciones de la cola: abrir WhatsApp, marcar enviado u omitido, y no quiere mensajes (BI-02).

Cada accion vuelve a validar el contacto contra la cola actual: el formulario no decide
por si solo a quien se le escribe. Abrir el enlace no marca nada como enviado.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app import db
from gastronomia.bi_models import GastronomiaBiContacto, GastronomiaBiEvento, GastronomiaBiNoContactar
from gastronomia.services.bi.cola import clave_contacto, construir_cola, contar_enviados_hoy, hoy_local, mensaje_para
from gastronomia.services.bi.cola_config import leer_config
from gastronomia.services.bi.historial import historial_clientes
from gastronomia.services.bi.whatsapp import url_wa_me

TIPO_ABIERTO = 'whatsapp_abierto'
TIPO_ENVIADO = 'mensaje_enviado'
TIPO_OMITIDO = 'mensaje_omitido'
TIPO_NO_CONTACTAR = 'no_contactar'

MSG_LIMITE = 'Llegaste al límite de mensajes de hoy. Mañana sigue la cola.'
MSG_NO_EN_COLA = 'Ese contacto ya no está en la cola. Recargá la página.'


def abrir_contacto(cliente_id: int, datos) -> str:
    """Registra la apertura y devuelve el enlace wa.me con el mensaje armado."""
    candidato = _candidato_validado(cliente_id, datos)
    if _limite_alcanzado(cliente_id):
        raise ValueError(MSG_LIMITE)
    _guardar_estado(cliente_id, candidato, 'abierto', TIPO_ABIERTO)
    url = url_wa_me(candidato['telefono'], mensaje_para(cliente_id, candidato))
    if not url:
        raise ValueError('No se pudo armar el enlace de WhatsApp para este contacto.')
    return url


def marcar_enviado(cliente_id: int, datos) -> None:
    candidato = _candidato_validado(cliente_id, datos)
    if _limite_alcanzado(cliente_id):
        raise ValueError(MSG_LIMITE)
    _guardar_estado(cliente_id, candidato, 'enviado', TIPO_ENVIADO)


def omitir_contacto(cliente_id: int, datos) -> None:
    candidato = _candidato_validado(cliente_id, datos)
    _guardar_estado(cliente_id, candidato, 'omitido', TIPO_OMITIDO)


def no_quiere_mensajes(cliente_id: int, datos) -> None:
    telefono = str(datos.get('telefono') or '').strip()
    if not telefono or telefono not in historial_clientes(cliente_id):
        raise ValueError('Ese contacto no está en tu historial de clientes.')
    if not GastronomiaBiNoContactar.query.filter_by(cliente_id=int(cliente_id), telefono_normalizado=telefono).first():
        db.session.add(GastronomiaBiNoContactar(cliente_id=int(cliente_id), telefono_normalizado=telefono))
    _registrar_evento(cliente_id, TIPO_NO_CONTACTAR, '')
    _confirmar()


def _datos_candidato(datos) -> tuple[str, str, int]:
    telefono = str(datos.get('telefono') or '').strip()
    segmento = str(datos.get('segmento') or '').strip()
    try:
        pedido = int(datos.get('pedido') or 0)
    except (TypeError, ValueError):
        pedido = 0
    if not telefono or not segmento or pedido <= 0:
        raise ValueError('Contacto inválido.')
    return telefono, segmento, pedido


def _candidato_validado(cliente_id: int, datos) -> dict:
    clave = _datos_candidato(datos)
    _, disponibles = construir_cola(cliente_id, hoy_local())
    for candidato in disponibles:
        if clave_contacto(candidato) == clave:
            return candidato
    raise ValueError(MSG_NO_EN_COLA)


def _limite_alcanzado(cliente_id: int) -> bool:
    return contar_enviados_hoy(cliente_id, hoy_local()) >= leer_config(cliente_id)['limite_dia']


def _guardar_estado(cliente_id: int, candidato: dict, estado: str, tipo_evento: str) -> None:
    ahora = datetime.utcnow()
    contacto = GastronomiaBiContacto.query.filter_by(
        cliente_id=int(cliente_id),
        telefono_normalizado=candidato['telefono'],
        segmento=candidato['segmento'],
        ultimo_pedido_id=int(candidato['ultimo_pedido_id']),
    ).first()
    if contacto is None:
        contacto = GastronomiaBiContacto(
            cliente_id=int(cliente_id),
            telefono_normalizado=candidato['telefono'],
            nombre=candidato['nombre'][:120],
            segmento=candidato['segmento'],
            ultimo_pedido_id=int(candidato['ultimo_pedido_id']),
            fecha_creacion=ahora,
        )
        db.session.add(contacto)
    contacto.estado = estado
    contacto.fecha_estado = ahora
    _registrar_evento(cliente_id, tipo_evento, candidato['segmento'])
    _confirmar()


def _registrar_evento(cliente_id: int, tipo: str, segmento: str) -> None:
    db.session.add(GastronomiaBiEvento(cliente_id=int(cliente_id), tipo=tipo, segmento=segmento))


def _confirmar() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('Ese contacto ya se registró. Recargá la página.')
