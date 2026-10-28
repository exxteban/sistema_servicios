"""Normalizacion de textos escritos a mano en planillas."""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation


def normalizar(valor) -> str:
    """Minusculas, sin tildes, sin signos y con espacios simples."""
    texto = str(valor or '').strip().lower()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.replace('�', 'n')
    texto = re.sub(r'[^a-z0-9/ ]+', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()


def parse_monto(valor) -> Decimal | None:
    """Acepta 28000, 28000.0, '28.000', 'Gs 28.000'."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float, Decimal)):
        return Decimal(str(valor)).quantize(Decimal('0.01'))
    texto = re.sub(r'[^0-9,.\-]', '', str(valor))
    if not texto or texto in {'-', '.', ','}:
        return None
    if ',' in texto and '.' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    elif texto.count('.') >= 1 and len(texto.rsplit('.', 1)[-1]) == 3:
        texto = texto.replace('.', '')
    elif ',' in texto:
        texto = texto.replace(',', '.') if len(texto.rsplit(',', 1)[-1]) != 3 else texto.replace(',', '')
    try:
        return Decimal(texto).quantize(Decimal('0.01'))
    except InvalidOperation:
        return None


def parse_cantidad(valor) -> int | None:
    monto = parse_monto(valor)
    if monto is None or monto <= 0:
        return None
    return max(int(monto), 1)
