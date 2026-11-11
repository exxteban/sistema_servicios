"""Comparacion "vs ayer hasta la misma hora" de los numeros del inicio.

Sin modelos a proposito: la usan servicios (app/services/dashboard_totales.py) y
gastronomia (gastronomia/services/dashboard_resumen_service.py), que se importa
mientras app.models todavia se esta cargando.
"""
from datetime import datetime, timedelta, timezone

from app.utils.helpers import formato_moneda_local, today_local, utc_bounds_for_local_dates


def ventana_ayer_misma_hora(ahora_utc=None):
    """[inicio de ayer, ayer a esta misma hora) en UTC naive, como guarda la base."""
    ahora_utc = ahora_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    ayer = today_local() - timedelta(days=1)
    inicio_ayer, fin_ayer = utc_bounds_for_local_dates(ayer, ayer)
    return inicio_ayer, min(ahora_utc - timedelta(days=1), fin_ayer)


def tendencia(hoy, ayer) -> str:
    """'mas' | 'menos' | 'igual', para pintar el texto de verde o rojo."""
    diferencia = round(float(hoy or 0) - float(ayer or 0))
    if diferencia > 0:
        return 'mas'
    return 'menos' if diferencia < 0 else 'igual'


def texto_diferencia_ventas(hoy: int, ayer: int) -> str:
    diferencia = int(hoy) - int(ayer)
    if diferencia == 0:
        return 'Igual que ayer'
    return f'{diferencia:+d} vs ayer'.replace('-', '−')


def texto_diferencia_monto(hoy: float, ayer: float) -> str:
    diferencia = round(float(hoy or 0) - float(ayer or 0))
    if diferencia == 0:
        return 'Igual que ayer'
    return f'{formato_moneda_local(abs(diferencia))} {"más" if diferencia > 0 else "menos"} que ayer'
