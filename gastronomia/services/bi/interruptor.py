"""Interruptor por instalacion de la experiencia comercial del BI (fase 8, liberacion gradual).

Apagarla solo oculta los bloques del tablero de Gastronomia. No borra nada: el historial, los contactos,
los consentimientos, la telemetria y la operacion (POS, cocina, caja, tienda) siguen funcionando.
Por defecto esta encendida, para no quitar nada a quien ya la usa; el root puede apagarla por instalacion.
"""
from __future__ import annotations

from app import db
from app.models import Configuracion
from gastronomia.services.bi.telemetria import TIPO_INTERRUPTOR, registrar_evento


def _clave(cliente_id: int) -> str:
    return f'gastronomia_bi_activo_{int(cliente_id)}'


def bi_activo(cliente_id: int) -> bool:
    return Configuracion.obtener_bool(_clave(cliente_id), default=True)


def cambiar_bi_activo(cliente_id: int, activo: bool) -> None:
    Configuracion.establecer_bool(
        _clave(cliente_id),
        activo,
        descripcion='Experiencia comercial del BI de gastronomia',
        commit=False,
    )
    registrar_evento(cliente_id, TIPO_INTERRUPTOR)
    db.session.commit()
