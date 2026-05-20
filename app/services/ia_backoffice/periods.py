from datetime import date, timedelta

from app.utils.helpers import today_local


PERIODOS_VALIDOS = {'hoy', 'ayer', '7d', '30d', 'mes', 'trimestre', 'anio', 'custom'}


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or '').strip())
    except Exception:
        return None


def normalizar_top_n(value, default: int = 5, maximo: int = 20) -> int:
    try:
        top_n = int(value)
    except Exception:
        top_n = default
    return max(1, min(top_n, maximo))


def resolver_rango(args: dict | None = None) -> dict:
    data = args or {}
    periodo = (data.get('periodo') or 'mes').strip().lower()
    if periodo not in PERIODOS_VALIDOS:
        periodo = 'mes'

    hoy = today_local()
    if periodo == 'hoy':
        desde = hasta = hoy
        label = 'Hoy'
    elif periodo == 'ayer':
        desde = hasta = hoy - timedelta(days=1)
        label = 'Ayer'
    elif periodo == '7d':
        desde, hasta, label = hoy - timedelta(days=6), hoy, 'Ultimos 7 dias'
    elif periodo == '30d':
        desde, hasta, label = hoy - timedelta(days=29), hoy, 'Ultimos 30 dias'
    elif periodo == 'trimestre':
        mes_inicio = ((hoy.month - 1) // 3) * 3 + 1
        desde, hasta, label = date(hoy.year, mes_inicio, 1), hoy, 'Este trimestre'
    elif periodo == 'anio':
        desde, hasta, label = date(hoy.year, 1, 1), hoy, 'Este anio'
    elif periodo == 'custom':
        desde = _parse_date(data.get('desde')) or hoy
        hasta = _parse_date(data.get('hasta')) or desde
        if desde > hasta:
            desde, hasta = hasta, desde
        label = f'{desde.isoformat()} al {hasta.isoformat()}'
    else:
        desde, hasta, label = hoy.replace(day=1), hoy, 'Este mes'

    dias = max((hasta - desde).days, 0)
    anterior_hasta = desde - timedelta(days=1)
    anterior_desde = anterior_hasta - timedelta(days=dias)
    return {
        'periodo': periodo,
        'desde': desde,
        'hasta': hasta,
        'periodo_label': label,
        'anterior_desde': anterior_desde,
        'anterior_hasta': anterior_hasta,
    }
