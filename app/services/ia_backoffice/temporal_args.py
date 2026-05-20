"""
Normalizacion deterministica de rangos relativos pedidos al asistente.
"""
import re
from datetime import date

from app.utils.helpers import today_local


MESES_RELATIVOS_RE = re.compile(
    r'(?:ultimos|ultimas|ultimo|ultima|en|desde|hace)\s+(\d{1,2})\s+mes(?:es)?'
)


def _normalizar_texto(texto: str) -> str:
    reemplazos = str.maketrans('áéíóúüñ', 'aeiouun')
    return (texto or '').lower().translate(reemplazos)


def _restar_meses(fecha: date, meses: int) -> date:
    mes_total = fecha.month - int(meses or 0)
    anio = fecha.year + (mes_total - 1) // 12
    mes = (mes_total - 1) % 12 + 1
    dias_mes = [31, 29 if anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(anio, mes, min(fecha.day, dias_mes[mes - 1]))


def normalizar_argumentos_temporales(argumentos: dict, consulta: str) -> dict:
    args = dict(argumentos or {})
    texto = _normalizar_texto(consulta)
    match = MESES_RELATIVOS_RE.search(texto)
    if not match:
        return args

    meses = max(1, min(int(match.group(1)), 24))
    hoy = today_local()
    args['periodo'] = 'custom'
    args['desde'] = _restar_meses(hoy, meses).isoformat()
    args['hasta'] = hoy.isoformat()
    return args
