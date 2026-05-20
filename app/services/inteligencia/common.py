from __future__ import annotations

from datetime import date

DIAS_STOCK_INMOVILIZADO = 60
SEMANAS_TENDENCIA_VENTAS = 6


def armar_metrica_monetaria(actual: float, anterior: float, titulo: str) -> dict:
    variacion = calcular_variacion(actual, anterior)
    return {
        'titulo': titulo,
        'actual': actual,
        'anterior': anterior,
        'actual_label': formatear_moneda(actual),
        'anterior_label': formatear_moneda(anterior),
        'variacion_label': variacion['label'],
        'direccion': variacion['direccion'],
    }


def armar_metrica_entera(actual: int, anterior: int, titulo: str) -> dict:
    variacion = calcular_variacion(actual, anterior)
    return {
        'titulo': titulo,
        'actual': actual,
        'anterior': anterior,
        'actual_label': str(actual),
        'anterior_label': str(anterior),
        'variacion_label': variacion['label'],
        'direccion': variacion['direccion'],
    }


def calcular_variacion(actual: float | int, anterior: float | int) -> dict:
    actual_num = float(actual or 0)
    anterior_num = float(anterior or 0)

    if anterior_num <= 0:
        if actual_num <= 0:
            return {'direccion': 'flat', 'label': 'Sin cambios'}
        return {'direccion': 'up', 'label': 'Sin base previa'}

    variacion = ((actual_num - anterior_num) / anterior_num) * 100
    if variacion > 0.1:
        direccion = 'up'
        prefijo = '+'
    elif variacion < -0.1:
        direccion = 'down'
        prefijo = ''
    else:
        direccion = 'flat'
        prefijo = ''

    return {
        'direccion': direccion,
        'label': f'{prefijo}{variacion:.1f}%',
    }


def formatear_moneda(valor: float) -> str:
    return f'₲ {valor:,.0f}'.replace(',', '.')


def formatear_rango(desde: date, hasta: date) -> str:
    return f'{desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}'
