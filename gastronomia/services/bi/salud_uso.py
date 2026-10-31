"""Panel de salud de uso para el usuario root de cada instalacion (BI-05, fase 3).

Lee solo los datos de esta instalacion: no centraliza ni compara con otras.

Semaforo, con reglas explicitas sobre la fecha local de hoy:
- Pedido: dias desde el ultimo pedido valido de cualquier canal (POS o tienda online).
- Uso del BI: dias desde la ultima accion registrada en el BI (telemetria; las vistas no cuentan).
- Activo: pedido en los ultimos 7 dias y uso del BI en los ultimos 30 dias.
- Inactivo: sin pedidos validos, o el ultimo tiene mas de 14 dias.
- En riesgo: el resto. Por ejemplo, pedidos recientes sin uso reciente del BI.
Sin datos, la metrica queda en None y se muestra como «sin datos», nunca como cero.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import func

from app import db
from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local
from gastronomia.models import GastronomiaPedido
from gastronomia.services.bi.activacion import lista_activacion
from gastronomia.services.bi.cola import construir_cola, hoy_local
from gastronomia.services.bi.pedidos_validos import CANAL_POS, CANAL_TIENDA, criterios_base
from gastronomia.services.bi.salud_funciones import uso_funciones
from gastronomia.services.bi.telemetria import TIPOS_COLA, ultimo_evento

ACTIVO = 'activo'
EN_RIESGO = 'en_riesgo'
INACTIVO = 'inactivo'
ETIQUETAS_SEMAFORO = {ACTIVO: 'Activo', EN_RIESGO: 'En riesgo', INACTIVO: 'Inactivo'}

DIAS_PEDIDO_RECIENTE = 7
DIAS_PEDIDO_MAXIMO = 14
DIAS_USO_BI_RECIENTE = 30
DIAS_COLA_SIN_ATENDER = 7
SEMANAS_TENDENCIA = 6


def dias_desde(fecha_local: date | None, hoy: date) -> int | None:
    if fecha_local is None:
        return None
    return max(0, (hoy - fecha_local).days)


def clasificar_semaforo(dias_pedido: int | None, dias_uso_bi: int | None) -> str:
    if dias_pedido is None or dias_pedido > DIAS_PEDIDO_MAXIMO:
        return INACTIVO
    bi_reciente = dias_uso_bi is not None and dias_uso_bi <= DIAS_USO_BI_RECIENTE
    if dias_pedido <= DIAS_PEDIDO_RECIENTE and bi_reciente:
        return ACTIVO
    return EN_RIESGO


def motivo_semaforo(estado: str, dias_pedido: int | None, dias_uso_bi: int | None) -> str:
    if dias_pedido is None:
        return 'Todavía no hay pedidos válidos.'
    if dias_pedido > DIAS_PEDIDO_MAXIMO:
        return f'El último pedido fue hace {dias_pedido} días.'
    if estado == ACTIVO:
        return 'Hay pedidos recientes y el BI se usó en el último mes.'
    if dias_pedido > DIAS_PEDIDO_RECIENTE:
        return f'El último pedido fue hace {dias_pedido} días.'
    if dias_uso_bi is None:
        return 'Hay pedidos recientes, pero el BI todavía no tiene acciones registradas.'
    return f'Hay pedidos recientes, pero la última acción en el BI fue hace {dias_uso_bi} días.'


def _fecha_local(momento_utc: datetime | None) -> date | None:
    return utc_naive_to_local(momento_utc).date() if momento_utc else None


def _ultimo_pedido(cliente_id: int, origen: str | None = None) -> datetime | None:
    consulta = db.session.query(func.max(GastronomiaPedido.fecha_creacion)).filter(*criterios_base(cliente_id))
    if origen:
        consulta = consulta.filter(GastronomiaPedido.origen_pedido == origen)
    return consulta.scalar()


def tendencia_semanal(cliente_id: int, hoy: date, semanas: int = SEMANAS_TENDENCIA) -> list[dict]:
    """Pedidos validos por semana (lunes a domingo), de la mas antigua a la semana en curso."""
    lunes_actual = hoy - timedelta(days=hoy.weekday())
    inicios = [lunes_actual - timedelta(weeks=n) for n in range(semanas - 1, -1, -1)]
    desde_utc, _ = utc_bounds_for_local_dates(inicios[0], hoy)
    fechas = (
        db.session.query(GastronomiaPedido.fecha_creacion)
        .filter(*criterios_base(cliente_id), GastronomiaPedido.fecha_creacion >= desde_utc)
        .all()
    )
    conteo: Counter = Counter()
    for (fecha_utc,) in fechas:
        dia = utc_naive_to_local(fecha_utc).date()
        conteo[dia - timedelta(days=dia.weekday())] += 1
    return [{'inicio': inicio, 'pedidos': conteo.get(inicio, 0)} for inicio in inicios]


def resumen_colas(cliente_id: int, hoy: date) -> dict:
    _, disponibles = construir_cola(cliente_id, hoy)
    ultimo_contacto = _fecha_local(ultimo_evento(cliente_id, TIPOS_COLA))
    dias_sin_contacto = dias_desde(ultimo_contacto, hoy)
    return {
        'en_cola': len(disponibles),
        'ultimo_contacto': ultimo_contacto,
        'dias_sin_contacto': dias_sin_contacto,
        'sin_atender': bool(disponibles) and (dias_sin_contacto is None or dias_sin_contacto > DIAS_COLA_SIN_ATENDER),
    }


def _porcentaje(completados: int, total: int) -> int:
    return round(completados * 100 / total) if total else 0


def resumen_salud_uso(cliente_id: int, hoy: date | None = None) -> dict:
    hoy = hoy or hoy_local()
    ultimo_pedido = _fecha_local(_ultimo_pedido(cliente_id))
    ultimo_bi = _fecha_local(ultimo_evento(cliente_id))
    dias_pedido = dias_desde(ultimo_pedido, hoy)
    dias_uso_bi = dias_desde(ultimo_bi, hoy)
    estado = clasificar_semaforo(dias_pedido, dias_uso_bi)
    activacion = lista_activacion(cliente_id)
    funciones = uso_funciones(cliente_id)
    return {
        'hoy': hoy,
        'semaforo': estado,
        'semaforo_label': ETIQUETAS_SEMAFORO[estado],
        'semaforo_motivo': motivo_semaforo(estado, dias_pedido, dias_uso_bi),
        'pedidos': {
            'ultimo': ultimo_pedido,
            'dias_sin_pedido': dias_pedido,
            'ultimo_pos': _fecha_local(_ultimo_pedido(cliente_id, CANAL_POS)),
            'ultimo_tienda': _fecha_local(_ultimo_pedido(cliente_id, CANAL_TIENDA)),
        },
        'bi': {'ultimo_uso': ultimo_bi, 'dias_sin_uso': dias_uso_bi},
        'activacion': {
            'completados': activacion['completados'],
            'total': activacion['total'],
            'porcentaje': _porcentaje(activacion['completados'], activacion['total']),
        },
        'colas': resumen_colas(cliente_id, hoy),
        'tendencia': tendencia_semanal(cliente_id, hoy),
        'funciones': funciones,
        'funciones_sin_usar': [funcion['nombre'] for funcion in funciones if not funcion['usada']],
    }
