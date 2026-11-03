"""Segmentos de la cola de clientes que vuelven (BI-02, plan seccion 7).

Reglas fijas, pensadas para poco historial:
- segunda_compra: una sola fecha de compra, hace entre `segunda_min` y `segunda_max` dias.
- habitual_ausente: al menos 3 fechas de compra y lleva mas dias sin comprar que su
  intervalo habitual (mediana de los dias entre compras), hasta DIAS_MAX_AUSENCIA.

Se cuentan fechas de compra distintas: dos pedidos el mismo dia cuentan como uno.
"""
from __future__ import annotations

from datetime import date
from statistics import median

SEGUNDA_COMPRA = 'segunda_compra'
HABITUAL_AUSENTE = 'habitual_ausente'
MIN_COMPRAS_HABITUAL = 3
DIAS_MAX_AUSENCIA = 120


def clasificar_segmentos(historial: dict, hoy: date, *, segunda_min: int, segunda_max: int) -> list[dict]:
    candidatos = []
    for cliente in historial.values():
        fechas = sorted(cliente.dias)
        if not fechas:
            continue
        sin_comprar = (hoy - fechas[-1]).days
        segmento, intervalo = _segmento(fechas, sin_comprar, segunda_min, segunda_max)
        if segmento:
            candidatos.append({
                'telefono': cliente.telefono,
                'nombre': cliente.nombre or 'Cliente',
                'segmento': segmento,
                'ultimo_pedido_id': cliente.ultimo_pedido_id,
                'ultima_compra': fechas[-1],
                'dias_sin_comprar': sin_comprar,
                'compras_dias': len(fechas),
                'intervalo_dias': intervalo,
                'plato_favorito': cliente.plato_favorito,
            })
    return candidatos


def _segmento(fechas: list[date], sin_comprar: int, segunda_min: int, segunda_max: int):
    if len(fechas) == 1:
        if segunda_min <= sin_comprar <= segunda_max:
            return SEGUNDA_COMPRA, None
        return None, None
    if len(fechas) < MIN_COMPRAS_HABITUAL:
        return None, None
    intervalo = median((b - a).days for a, b in zip(fechas, fechas[1:]))
    if intervalo < sin_comprar <= DIAS_MAX_AUSENCIA:
        return HABITUAL_AUSENTE, round(intervalo)
    return None, None
