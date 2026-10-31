"""Bloque «Clientes que vuelven» del tab Gastronomia, con degradacion segura (BI-02).

Si el calculo falla, solo se oculta este bloque: el resto del tablero y la operacion no dependen de el.
"""
from __future__ import annotations

from datetime import date

from flask import current_app, has_app_context

from gastronomia.services.bi.cola import resumen_cola
from gastronomia.services.bi.retorno import resumen_retorno


def resumen_clientes_vuelven(cliente_id: int, hoy: date | None = None) -> dict:
    return {
        'disponible': True,
        'cola': resumen_cola(cliente_id, hoy),
        'retorno': resumen_retorno(cliente_id),
    }


def resumen_clientes_vuelven_seguro(cliente_id: int, hoy: date | None = None) -> dict:
    try:
        return resumen_clientes_vuelven(cliente_id, hoy)
    except Exception:
        if has_app_context():
            current_app.logger.exception('No se pudo construir el bloque Clientes que vuelven.')
        return {'disponible': False}
