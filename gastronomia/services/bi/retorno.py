"""Compras despues del mensaje marcado como enviado (BI-02).

Describe el orden en el tiempo: «volvio despues del mensaje», sin afirmar causalidad.
Solo cuentan los envios cuya ventana de observacion ya cerro; el resto queda en observacion.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from gastronomia.bi_models import GastronomiaBiContacto
from gastronomia.services.bi.historial import historial_clientes
from gastronomia.services.bi.segmentos import HABITUAL_AUSENTE, SEGUNDA_COMPRA

VENTANA_DIAS = {SEGUNDA_COMPRA: 15, HABITUAL_AUSENTE: 30}
DIAS_REPORTE = 60


def resumen_retorno(cliente_id: int, ahora: datetime | None = None) -> dict:
    ahora = ahora or datetime.utcnow()
    desde = ahora - timedelta(days=DIAS_REPORTE)
    envios = GastronomiaBiContacto.query.filter(
        GastronomiaBiContacto.cliente_id == int(cliente_id),
        GastronomiaBiContacto.estado == 'enviado',
        GastronomiaBiContacto.fecha_estado >= desde,
    ).all()
    historial = historial_clientes(cliente_id)
    cerrados = volvieron = en_observacion = 0
    for envio in envios:
        ventana = timedelta(days=VENTANA_DIAS.get(envio.segmento, VENTANA_DIAS[SEGUNDA_COMPRA]))
        fin = envio.fecha_estado + ventana
        if fin > ahora:
            en_observacion += 1
            continue
        cerrados += 1
        cliente = historial.get(envio.telefono_normalizado)
        if cliente and any(envio.fecha_estado < fecha <= fin for fecha in cliente.fechas):
            volvieron += 1
    return {
        'dias': DIAS_REPORTE,
        'enviados_cerrados': cerrados,
        'volvieron': volvieron,
        'en_observacion': en_observacion,
    }
