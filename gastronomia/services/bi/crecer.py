"""Bloque Crecer del tab Gastronomia: activacion y canales, con degradacion segura.

Si el calculo falla, solo se oculta este bloque: el resto del tablero y la operacion
(pedidos, cocina, caja) no dependen de el.
"""
from __future__ import annotations

from flask import current_app, has_app_context

from gastronomia.services.bi.activacion import lista_activacion
from gastronomia.services.bi.canales import indicadores_canales
from gastronomia.services.bi.embudo import resumen_embudo_seguro
from gastronomia.services.bi.materiales import materiales_activacion


def resumen_crecer(cliente_id: int, periodo: dict) -> dict:
    return {
        'disponible': True,
        'activacion': lista_activacion(cliente_id),
        'materiales': materiales_activacion(cliente_id),
        'canales': indicadores_canales(cliente_id, periodo),
        'embudo': resumen_embudo_seguro(cliente_id),
    }


def resumen_crecer_seguro(cliente_id: int, periodo: dict) -> dict:
    try:
        return resumen_crecer(cliente_id, periodo)
    except Exception:
        if has_app_context():
            current_app.logger.exception('No se pudo construir el bloque Crecer de gastronomia.')
        return {'disponible': False}
