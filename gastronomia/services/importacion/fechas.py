"""Lectura tolerante de fechas escritas a mano ('07de cotubre', '15/0ct')."""
from __future__ import annotations

import difflib
import re
from datetime import date, datetime

from gastronomia.services.importacion.texto import normalizar


MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
    'noviembre': 11, 'diciembre': 12,
}
ABREVIATURAS = {nombre[:3]: numero for nombre, numero in MESES.items()}


def parse_fecha(valor, anio_defecto: int) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)) and 30000 < float(valor) < 80000:
        return _fecha_serial_excel(float(valor))
    texto = normalizar(valor)
    if not texto or not re.search(r'\d', texto):
        return None
    return _fecha_numerica(texto, anio_defecto) or _fecha_con_mes_texto(texto, anio_defecto)


def _fecha_serial_excel(serial: float) -> date | None:
    try:
        return date.fromordinal(date(1899, 12, 30).toordinal() + int(serial))
    except ValueError:
        return None


def _fecha_numerica(texto: str, anio_defecto: int) -> date | None:
    match = re.fullmatch(r'(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?', texto)
    if not match:
        return None
    dia, mes = int(match.group(1)), int(match.group(2))
    anio = _anio(match.group(3), anio_defecto)
    return _fecha_segura(anio, mes, dia)


def _fecha_con_mes_texto(texto: str, anio_defecto: int) -> date | None:
    match = re.match(r'(\d{1,2})', texto)
    if not match:
        return None
    dia = int(match.group(1))
    resto = texto[match.end():]
    # Un cero escrito en lugar de la "o" (0ct) es comun en planillas a mano.
    resto = re.sub(r'(?<=\b)0(?=[a-z])|(?<=[a-z])0', 'o', resto)
    resto = re.sub(r'^\s*(de|del)\s*|^de(?=[a-z])', ' ', resto.replace('/', ' ')).strip()
    anio_match = re.search(r'(\d{2,4})\s*$', resto)
    anio = _anio(anio_match.group(1) if anio_match else None, anio_defecto)
    palabras = re.findall(r'[a-z]+', resto)
    for palabra in palabras:
        if palabra in {'de', 'del'}:
            continue
        mes = _mes_desde_palabra(palabra)
        if mes:
            return _fecha_segura(anio, mes, dia)
    return None


def _mes_desde_palabra(palabra: str) -> int | None:
    if palabra.startswith('de') and len(palabra) > 4:
        palabra = palabra[2:]
    if palabra in MESES:
        return MESES[palabra]
    if len(palabra) == 3 and palabra in ABREVIATURAS:
        return ABREVIATURAS[palabra]
    candidatos = difflib.get_close_matches(palabra, list(MESES), n=1, cutoff=0.7)
    if candidatos:
        return MESES[candidatos[0]]
    abreviado = difflib.get_close_matches(palabra[:3], list(ABREVIATURAS), n=1, cutoff=0.67)
    return ABREVIATURAS[abreviado[0]] if abreviado and len(palabra) <= 4 else None


def _anio(texto: str | None, anio_defecto: int) -> int:
    if not texto:
        return anio_defecto
    anio = int(texto)
    return anio + 2000 if anio < 100 else anio


def _fecha_segura(anio: int, mes: int, dia: int) -> date | None:
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None
