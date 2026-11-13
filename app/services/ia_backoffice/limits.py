"""
Validaciones de presupuesto para el asistente IA interno.
"""
from datetime import date, datetime, time, timedelta, timezone

from app.services.ia_backoffice.audit import obtener_consumo_tokens
from app.services.ia_backoffice.settings import obtener_configuracion_asistente
from app.utils.helpers import get_app_timezone


def _to_utc_naive(local_date: date, local_time: time) -> datetime:
    local_dt = datetime.combine(local_date, local_time, tzinfo=get_app_timezone())
    return local_dt.astimezone(timezone.utc).replace(tzinfo=None)


def _rango_dia_utc(ahora: datetime | None = None) -> tuple[datetime, datetime]:
    ahora_local = ahora.astimezone(get_app_timezone()) if ahora and ahora.tzinfo else (ahora or datetime.now(get_app_timezone()))
    dia = ahora_local.date()
    return _to_utc_naive(dia, time.min), _to_utc_naive(dia + timedelta(days=1), time.min)


def _rango_mes_utc(ahora: datetime | None = None) -> tuple[datetime, datetime]:
    ahora_local = ahora.astimezone(get_app_timezone()) if ahora and ahora.tzinfo else (ahora or datetime.now(get_app_timezone()))
    primero = ahora_local.date().replace(day=1)
    if primero.month == 12:
        siguiente = primero.replace(year=primero.year + 1, month=1)
    else:
        siguiente = primero.replace(month=primero.month + 1)
    return _to_utc_naive(primero, time.min), _to_utc_naive(siguiente, time.min)


def obtener_rangos_presupuesto(ahora: datetime | None = None) -> dict:
    dia_desde, dia_hasta = _rango_dia_utc(ahora)
    mes_desde, mes_hasta = _rango_mes_utc(ahora)
    return {
        'dia': {'desde': dia_desde, 'hasta': dia_hasta},
        'mes': {'desde': mes_desde, 'hasta': mes_hasta},
    }


def validar_presupuesto_tokens(tokens_estimados: int = 0, usuario=None, ahora: datetime | None = None) -> tuple[bool, str]:
    cfg = obtener_configuracion_asistente()
    estimado = max(0, int(tokens_estimados or 0))
    rangos = obtener_rangos_presupuesto(ahora)

    if cfg.daily_token_budget:
        consumo_dia = obtener_consumo_tokens(rangos['dia']['desde'], rangos['dia']['hasta'], usuario=usuario)
        if consumo_dia['tokens_total'] + estimado > cfg.daily_token_budget:
            return False, 'presupuesto_diario_excedido'
    if cfg.monthly_token_budget:
        # Cuota mensual de la instalacion (el cliente): suma a todos los usuarios. La diaria sigue por usuario
        # para que una sola persona no consuma la cuota de todos.
        consumo_mes = obtener_consumo_tokens(rangos['mes']['desde'], rangos['mes']['hasta'])
        if consumo_mes['tokens_total'] + estimado > cfg.monthly_token_budget:
            return False, 'presupuesto_mensual_excedido'
    return True, 'ok'


CONTACTO_AMPLIAR = 'Si necesitas mas, habla con el administrador para ampliar la cuota de uso de la IA.'


def mensaje_presupuesto_excedido(motivo: str) -> str:
    if motivo == 'presupuesto_diario_excedido':
        return f'Alcanzaste el limite diario de uso de la IA. Se renueva manana. {CONTACTO_AMPLIAR}'
    if motivo == 'presupuesto_mensual_excedido':
        return f'Se alcanzo el limite mensual de uso de la IA. Se renueva el 1 del mes que viene. {CONTACTO_AMPLIAR}'
    return f'Se alcanzo el limite de uso de la IA. {CONTACTO_AMPLIAR}'
