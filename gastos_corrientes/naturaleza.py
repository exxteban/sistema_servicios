"""Naturalezas contables de los gastos corrientes.

La categoria explica de que es el pago. La naturaleza define si reduce el resultado
del negocio o si es un retiro personal del dueno. Son ejes distintos y no deben
inferirse uno del otro.
"""

NATURALEZA_GASTO_NEGOCIO = 'gasto_negocio'
NATURALEZA_RETIRO_DUENO = 'retiro_dueno'

NATURALEZAS_CONTABLES = (
    (
        NATURALEZA_GASTO_NEGOCIO,
        'Gasto del negocio',
        'Reduce la ganancia porque fue necesario para operar el negocio.',
    ),
    (
        NATURALEZA_RETIRO_DUENO,
        'Retiro personal',
        'La plata sale, pero no reduce la ganancia: se retira desde la utilidad.',
    ),
)

CLAVES_NATURALEZAS = {clave for clave, _etiqueta, _ayuda in NATURALEZAS_CONTABLES}


def normalizar_naturaleza(valor: str | None) -> str:
    clave = (valor or '').strip().lower()
    return clave if clave in CLAVES_NATURALEZAS else NATURALEZA_GASTO_NEGOCIO


def es_retiro_dueno(valor: str | None) -> bool:
    return normalizar_naturaleza(valor) == NATURALEZA_RETIRO_DUENO
