"""Canal propio frente a plataformas externas, por semana, con cobertura de identidad."""
from __future__ import annotations

from datetime import timedelta

from gastronomia.services.bi.identidad import cobertura_identidad
from gastronomia.services.bi.pedidos_validos import (
    GRUPO_DESCONOCIDO,
    GRUPO_PLATAFORMA,
    GRUPO_PROPIO,
    filas_pedidos_validos,
)
from gastronomia.services.channel_price_service import CANALES_PRECIOS

GRUPOS = (GRUPO_PROPIO, GRUPO_PLATAFORMA, GRUPO_DESCONOCIDO)


def indicadores_canales(cliente_id: int, periodo: dict) -> dict:
    filas = filas_pedidos_validos(cliente_id, periodo)
    total = len(filas)
    return {
        'total_pedidos': total,
        'ventas_total': _ventas(filas),
        'grupos': {
            grupo: _resumen_filas([fila for fila in filas if fila['grupo'] == grupo], total)
            for grupo in GRUPOS
        },
        'plataformas': {
            canal: _resumen_filas([fila for fila in filas if fila['canal'] == canal], total)
            for canal in CANALES_PRECIOS
        },
        'identidad': cobertura_identidad(filas),
        'semanas': _semanas(filas),
    }


def _ventas(filas: list[dict]) -> float:
    return round(sum(fila['total'] for fila in filas), 2)


def _resumen_filas(filas: list[dict], total: int) -> dict:
    pedidos = len(filas)
    return {
        'pedidos': pedidos,
        'ventas': _ventas(filas),
        'participacion': round(pedidos * 100 / total, 1) if total else None,
        'identidad': cobertura_identidad(filas),
    }


def _semanas(filas: list[dict]) -> list[dict]:
    """Solo semanas con pedidos: una semana sin datos no se muestra como cero."""
    por_semana: dict = {}
    for fila in filas:
        inicio = fila['fecha_local'] - timedelta(days=fila['fecha_local'].weekday())
        semana = por_semana.setdefault(inicio, {
            'inicio': inicio,
            GRUPO_PROPIO: 0,
            GRUPO_PLATAFORMA: 0,
            GRUPO_DESCONOCIDO: 0,
        })
        semana[fila['grupo']] += 1
    return [por_semana[inicio] for inicio in sorted(por_semana)]
