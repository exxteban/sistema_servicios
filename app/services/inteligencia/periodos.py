from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func

from app import db
from app.models import Venta
from app.utils.helpers import utc_naive_to_local

PERIODO_MES = 'mes'
PERIODO_30D = '30d'
PERIODO_TRIMESTRE = 'trimestre'
PERIODO_TODO = 'todo'
PERIODO_DEFAULT = PERIODO_MES

PERIODOS_INTELIGENCIA = (
    {'valor': PERIODO_MES, 'label': 'Este mes'},
    {'valor': PERIODO_30D, 'label': 'Últimos 30 días'},
    {'valor': PERIODO_TRIMESTRE, 'label': 'Este trimestre'},
    {'valor': PERIODO_TODO, 'label': 'Todo período'},
)

PERIODOS_INTELIGENCIA_MAP = {item['valor']: item['label'] for item in PERIODOS_INTELIGENCIA}


def normalizar_periodo(periodo: str | None) -> str:
    valor = (periodo or '').strip().lower()
    if valor in PERIODOS_INTELIGENCIA_MAP:
        return valor
    return PERIODO_DEFAULT


def obtener_opciones_periodo(periodo_activo: str | None = None) -> list[dict]:
    activo = normalizar_periodo(periodo_activo)
    return [
        {
            'valor': item['valor'],
            'label': item['label'],
            'activo': item['valor'] == activo,
        }
        for item in PERIODOS_INTELIGENCIA
    ]


def obtener_label_periodo(periodo: str | None) -> str:
    return PERIODOS_INTELIGENCIA_MAP[normalizar_periodo(periodo)]


def resolver_periodos(fecha_corte: date, periodo: str | None = None) -> tuple[dict, dict]:
    periodo_normalizado = normalizar_periodo(periodo)
    if periodo_normalizado == PERIODO_30D:
        return _resolver_periodo_30_dias(fecha_corte)
    if periodo_normalizado == PERIODO_TRIMESTRE:
        return _resolver_periodo_trimestre(fecha_corte)
    if periodo_normalizado == PERIODO_TODO:
        return _resolver_periodo_todo(fecha_corte)
    return _resolver_periodo_mes(fecha_corte)


def _resolver_periodo_mes(fecha_corte: date) -> tuple[dict, dict]:
    inicio_actual = fecha_corte.replace(day=1)
    dias_periodo = max((fecha_corte - inicio_actual).days, 0)
    return _construir_periodos(fecha_corte, dias_periodo)


def _resolver_periodo_30_dias(fecha_corte: date) -> tuple[dict, dict]:
    return _construir_periodos(fecha_corte, 29)


def _resolver_periodo_trimestre(fecha_corte: date) -> tuple[dict, dict]:
    mes_inicio_trimestre = ((fecha_corte.month - 1) // 3) * 3 + 1
    inicio_actual = date(fecha_corte.year, mes_inicio_trimestre, 1)
    dias_periodo = max((fecha_corte - inicio_actual).days, 0)
    return _construir_periodos(fecha_corte, dias_periodo)


def _resolver_periodo_todo(fecha_corte: date) -> tuple[dict, dict]:
    inicio_actual = _obtener_primera_fecha_venta() or fecha_corte
    dias_periodo = max((fecha_corte - inicio_actual).days, 0)
    return _construir_periodos(fecha_corte, dias_periodo)


def _obtener_primera_fecha_venta() -> date | None:
    fecha_utc = (
        db.session.query(func.min(Venta.fecha_venta))
        .filter(Venta.estado == 'completada')
        .scalar()
    )
    fecha_local = utc_naive_to_local(fecha_utc)
    return fecha_local.date() if fecha_local else None


def _construir_periodos(fin_actual: date, dias_periodo: int) -> tuple[dict, dict]:
    inicio_actual = fin_actual - timedelta(days=dias_periodo)
    fin_anterior = inicio_actual - timedelta(days=1)
    inicio_anterior = fin_anterior - timedelta(days=dias_periodo)
    return (
        {'desde': inicio_actual, 'hasta': fin_actual},
        {'desde': inicio_anterior, 'hasta': fin_anterior},
    )
