"""Reporte de valor del mes para el dueno (BI-03, fase 3 del plan).

Definiciones:
- Pedidos y ventas: pedidos validos por fecha de creacion, con el total del pedido.
- Comparacion: los mismos dias del mes anterior (periodos equivalentes).
- Clientes nuevos: telefonos cuya primera compra valida cae en el mes. Nunca se agrupa por nombre.
- Mensajes: envios marcados como enviados en el mes; «volvieron» solo con ventana cerrada.
- Acompanamientos: medicion del sugeridor, por fecha de cobro, con el importe de los renglones aceptados.
- Comision evitada: ventas de cada plataforma por el porcentaje configurado. Es una estimacion.

Una metrica sin datos queda en None y se muestra como no disponible, nunca como cero.
La redaccion es «despues de», sin afirmar causa.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import current_app, has_app_context

from app.utils.helpers import today_local, utc_bounds_for_local_dates
from gastronomia.services.bi.canales import indicadores_canales
from gastronomia.services.bi.comision import leer_porcentajes
from gastronomia.services.bi.historial import historial_clientes
from gastronomia.services.bi.pedidos_validos import GRUPO_PLATAFORMA, GRUPO_PROPIO
from gastronomia.services.bi.retorno import resumen_envios
from gastronomia.services.channel_price_service import CANALES_PRECIOS
from gastronomia.services.sugerencias.medicion import resumen_seguro as resumen_sugerencias


def periodos(hoy: date) -> tuple[dict, dict]:
    """Mes en curso hasta hoy, y el mes anterior en la misma cantidad de dias."""
    inicio_actual = hoy.replace(day=1)
    fin_anterior = inicio_actual - timedelta(days=1)
    inicio_anterior = fin_anterior.replace(day=1)
    dia_equivalente = min(hoy.day, fin_anterior.day)
    return (
        {'desde': inicio_actual, 'hasta': hoy},
        {'desde': inicio_anterior, 'hasta': inicio_anterior.replace(day=dia_equivalente)},
    )


def variacion(actual: float, anterior: float) -> float | None:
    """Variacion porcentual frente al periodo anterior; None si ese periodo no tiene base."""
    if not anterior:
        return None
    return round((actual - anterior) * 100 / anterior, 1)


def clientes_nuevos_identificados(cliente_id: int, periodo: dict) -> int:
    historial = historial_clientes(cliente_id)
    return sum(
        1 for cliente in historial.values()
        if periodo['desde'] <= min(cliente.dias) <= periodo['hasta']
    )


def _pedidos_y_ventas(canales: dict) -> dict:
    return {
        'pedidos': canales['total_pedidos'],
        'ventas': canales['ventas_total'],
        'propios': canales['grupos'][GRUPO_PROPIO],
        'plataformas': canales['grupos'][GRUPO_PLATAFORMA],
    }


def _comparacion(actual: dict, anterior: dict) -> dict:
    return {
        'pedidos': variacion(actual['total_pedidos'], anterior['total_pedidos']),
        'ventas': variacion(actual['ventas_total'], anterior['ventas_total']),
        'ventas_propias': variacion(
            actual['grupos'][GRUPO_PROPIO]['ventas'], anterior['grupos'][GRUPO_PROPIO]['ventas'],
        ),
    }


def _comision_evitada(canales: dict, porcentajes: dict) -> dict | None:
    activas = {canal: pct for canal, pct in porcentajes.items() if pct}
    if not activas:
        return None
    detalle = [
        {
            'canal': canal,
            'nombre': CANALES_PRECIOS[canal],
            'porcentaje': pct,
            'ventas': canales['plataformas'][canal]['ventas'],
            'monto': round(canales['plataformas'][canal]['ventas'] * pct / 100, 2),
        }
        for canal, pct in activas.items()
    ]
    return {'monto': round(sum(fila['monto'] for fila in detalle), 2), 'detalle': detalle}


def _mensajes(cliente_id: int, periodo: dict, ahora: datetime) -> dict:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    return resumen_envios(cliente_id, inicio, fin, ahora)


def _acompanamientos(cliente_id: int, periodo: dict) -> dict | None:
    resumen = resumen_sugerencias(cliente_id, periodo)
    if resumen is None:
        return None
    return {
        'pedidos': resumen['pedidos'],
        'renglones': resumen['renglones'],
        'importe': resumen['importe'],
    }


def resumen_reporte_valor(cliente_id: int, hoy: date | None = None, ahora: datetime | None = None) -> dict:
    hoy = hoy or today_local()
    ahora = ahora or datetime.utcnow()
    actual, anterior = periodos(hoy)
    canales_actual = indicadores_canales(cliente_id, actual)
    canales_anterior = indicadores_canales(cliente_id, anterior)
    porcentajes = leer_porcentajes(cliente_id)
    return {
        'disponible': True,
        'periodo_label': f'{actual["desde"]:%d/%m} al {actual["hasta"]:%d/%m/%Y}',
        'pedidos': _pedidos_y_ventas(canales_actual),
        'comparacion': _comparacion(canales_actual, canales_anterior),
        'identidad': canales_actual['identidad'],
        'clientes_nuevos': clientes_nuevos_identificados(cliente_id, actual),
        'mensajes': _mensajes(cliente_id, actual, ahora),
        'acompanamientos': _acompanamientos(cliente_id, actual),
        'comision': _comision_evitada(canales_actual, porcentajes),
        'porcentajes': [
            {'canal': canal, 'nombre': nombre, 'porcentaje': porcentajes[canal]}
            for canal, nombre in CANALES_PRECIOS.items()
        ],
    }


def resumen_reporte_valor_seguro(cliente_id: int, hoy: date | None = None, ahora: datetime | None = None) -> dict:
    try:
        return resumen_reporte_valor(cliente_id, hoy, ahora)
    except Exception:
        if has_app_context():
            current_app.logger.exception('No se pudo construir el reporte de valor de gastronomia.')
        return {'disponible': False}
