"""Telemetria minima del BI de gastronomia: cada accion que cambia datos deja un evento por instalacion (BI-05).

Las vistas no se registran: cada carga del tablero escribiria en la base. Se registran solo las acciones
del dueno que cambian algo: contactos de la cola, pasos de activacion, comisiones y configuracion de la cola.
El evento se agrega a la sesion; quien llama confirma la transaccion junto con su propia accion.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func

from app import db
from gastronomia.bi_models import GastronomiaBiEvento

TIPO_ABIERTO = 'whatsapp_abierto'
TIPO_ENVIADO = 'mensaje_enviado'
TIPO_OMITIDO = 'mensaje_omitido'
TIPO_NO_CONTACTAR = 'no_contactar'
TIPO_ACTIVACION = 'activacion_marcada'
TIPO_COMISION = 'comision_guardada'
TIPO_CONFIG_COLA = 'config_cola_guardada'

TIPOS_COLA = (TIPO_ABIERTO, TIPO_ENVIADO, TIPO_OMITIDO, TIPO_NO_CONTACTAR)


def registrar_evento(cliente_id: int, tipo: str, segmento: str = '') -> None:
    db.session.add(GastronomiaBiEvento(cliente_id=int(cliente_id), tipo=tipo, segmento=segmento))


def ultimo_evento(cliente_id: int, tipos: tuple[str, ...] | None = None) -> datetime | None:
    """Fecha UTC del evento mas reciente del cliente, opcionalmente filtrado por tipo."""
    consulta = db.session.query(func.max(GastronomiaBiEvento.fecha)).filter(
        GastronomiaBiEvento.cliente_id == int(cliente_id),
    )
    if tipos:
        consulta = consulta.filter(GastronomiaBiEvento.tipo.in_(tipos))
    return consulta.scalar()


def existe_evento(cliente_id: int, tipos: tuple[str, ...]) -> bool:
    return GastronomiaBiEvento.query.filter(
        GastronomiaBiEvento.cliente_id == int(cliente_id),
        GastronomiaBiEvento.tipo.in_(tipos),
    ).first() is not None
