from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

from control_de_empleados.models import Empleado, EmpleadoAusencia, EmpleadoFeriado
from control_de_empleados.services.tipos_ausencia import (
    TIPOS_AUSENCIA_BASE_VALIDOS,
    opciones_tipos_ausencia as construir_opciones_tipos_ausencia,
    obtener_tipos_validos_ausencia,
)

ESTADOS_AUSENCIA = [
    ('pendiente', 'Pendiente'),
    ('aprobado', 'Aprobado'),
    ('tomado', 'Tomado'),
    ('rechazado', 'Rechazado'),
]

TIPOS_AUSENCIA_VALIDOS = set(TIPOS_AUSENCIA_BASE_VALIDOS)
ESTADOS_AUSENCIA_VALIDOS = {valor for valor, _ in ESTADOS_AUSENCIA}
ESTADOS_AUSENCIA_CONFIRMADOS = {'aprobado', 'tomado'}
ESTADOS_AUSENCIA_RESERVAN_VACACIONES = {'pendiente', 'aprobado', 'tomado'}
ESTADOS_AUSENCIA_BLOQUEAN_SOLAPE = {'pendiente', 'aprobado', 'tomado'}
FERIADOS_FIJOS_PARAGUAY = {
    (1, 1),
    (3, 1),
    (5, 1),
    (5, 14),
    (5, 15),
    (6, 12),
    (6, 20),
    (8, 15),
    (9, 29),
    (12, 8),
    (12, 25),
}


def opciones_tipos_ausencia(cliente_id: int | None = None) -> list[dict]:
    return construir_opciones_tipos_ausencia(cliente_id)


def opciones_estados_ausencia() -> list[dict]:
    return [{'valor': valor, 'label': label} for valor, label in ESTADOS_AUSENCIA]


def normalizar_anio(raw_value: str | None, periodo: str | None = None) -> int:
    referencia = date.today().year
    if periodo and len(periodo) >= 4 and periodo[:4].isdigit():
        referencia = int(periodo[:4])
    texto = (raw_value or '').strip()
    if texto.isdigit():
        valor = int(texto)
        if 2000 <= valor <= 2100:
            return valor
    return referencia


def normalizar_filtro_tipo(raw_value: str | None, cliente_id: int | None = None) -> str:
    valor = (raw_value or '').strip().lower()
    return valor if valor in obtener_tipos_validos_ausencia(cliente_id) else ''


def normalizar_filtro_estado(raw_value: str | None) -> str:
    valor = (raw_value or '').strip().lower()
    return valor if valor in ESTADOS_AUSENCIA_VALIDOS else ''


def normalizar_filtros_ausencias(
    args,
    periodo: str | None = None,
    cliente_id: int | None = None,
) -> dict:
    page = getattr(args, 'get', lambda *_args, **_kwargs: 1)('page_ausencias', 1, type=int)
    return {
        'anio': normalizar_anio(getattr(args, 'get', lambda *_args, **_kwargs: None)('anio'), periodo),
        'tipo': normalizar_filtro_tipo(
            getattr(args, 'get', lambda *_args, **_kwargs: None)('tipo_ausencia'),
            cliente_id=cliente_id,
        ),
        'estado': normalizar_filtro_estado(getattr(args, 'get', lambda *_args, **_kwargs: None)('estado_ausencia')),
        'page': page if page and page > 0 else 1,
    }


def calcular_dias_inclusive(fecha_desde: date | None, fecha_hasta: date | None) -> int:
    if not fecha_desde or not fecha_hasta or fecha_hasta < fecha_desde:
        return 0
    return (fecha_hasta - fecha_desde).days + 1


def _calcular_domingo_pascua(anio: int) -> date:
    a = anio % 19
    b = anio // 100
    c = anio % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


@lru_cache(maxsize=32)
def obtener_feriados_base_paraguay(anio: int) -> frozenset[date]:
    pascua = _calcular_domingo_pascua(anio)
    feriados = {date(anio, mes, dia) for mes, dia in FERIADOS_FIJOS_PARAGUAY}
    feriados.add(pascua - timedelta(days=3))
    feriados.add(pascua - timedelta(days=2))
    return frozenset(feriados)


def obtener_feriados_personalizados(
    cliente_id: int | None,
    anios: list[int],
) -> dict[int, set[date]]:
    years = sorted(set(anios))
    resultado = {anio: set() for anio in years}
    if not years or not cliente_id:
        return resultado

    fecha_inicio = date(min(years), 1, 1)
    fecha_fin = date(max(years), 12, 31)
    feriados = EmpleadoFeriado.query.filter(
        EmpleadoFeriado.cliente_id == cliente_id,
        EmpleadoFeriado.fecha >= fecha_inicio,
        EmpleadoFeriado.fecha <= fecha_fin,
    ).all()
    for feriado in feriados:
        resultado.setdefault(feriado.fecha.year, set()).add(feriado.fecha)
    return resultado


def construir_calendario_feriados(
    anios: list[int],
    cliente_id: int | None = None,
) -> dict[int, set[date]]:
    years = sorted(set(anios))
    personalizados = obtener_feriados_personalizados(cliente_id, years)
    calendario: dict[int, set[date]] = {}
    for anio in years:
        calendario[anio] = set(obtener_feriados_base_paraguay(anio))
        calendario[anio].update(personalizados.get(anio, set()))
    return calendario


def es_dia_habil_vacaciones(
    fecha: date,
    feriados_por_anio: dict[int, set[date]] | None = None,
) -> bool:
    if fecha.weekday() == 6:
        return False
    if feriados_por_anio is None:
        return fecha not in obtener_feriados_base_paraguay(fecha.year)
    return fecha not in feriados_por_anio.get(fecha.year, set())


def calcular_dias_habiles_paraguay(
    fecha_desde: date | None,
    fecha_hasta: date | None,
    feriados_por_anio: dict[int, set[date]] | None = None,
) -> int:
    if not fecha_desde or not fecha_hasta or fecha_hasta < fecha_desde:
        return 0
    total = 0
    actual = fecha_desde
    while actual <= fecha_hasta:
        if es_dia_habil_vacaciones(actual, feriados_por_anio=feriados_por_anio):
            total += 1
        actual += timedelta(days=1)
    return total


def calcular_dias_ausencia_en_rango(
    ausencia: EmpleadoAusencia,
    fecha_inicio: date,
    fecha_fin: date,
    feriados_por_anio: dict[int, set[date]] | None = None,
) -> int:
    inicio = max(ausencia.fecha_desde, fecha_inicio)
    fin = min(ausencia.fecha_hasta, fecha_fin)
    return calcular_dias_habiles_paraguay(inicio, fin, feriados_por_anio=feriados_por_anio)


def obtener_saldos_vacaciones_por_anio(
    empleado: Empleado,
    anios: list[int],
    cliente_id: int | None = None,
    excluir_id: int | None = None,
) -> dict[int, dict]:
    saldos: dict[int, dict] = {}
    feriados_por_anio = construir_calendario_feriados(anios, cliente_id=cliente_id)
    for anio in sorted(set(anios)):
        inicio_anio = date(anio, 1, 1)
        fin_anio = date(anio, 12, 31)
        query = empleado.ausencias.filter(
            EmpleadoAusencia.tipo == 'vacaciones',
            EmpleadoAusencia.estado.in_(tuple(ESTADOS_AUSENCIA_RESERVAN_VACACIONES)),
            EmpleadoAusencia.fecha_desde <= fin_anio,
            EmpleadoAusencia.fecha_hasta >= inicio_anio,
        )
        if excluir_id:
            query = query.filter(EmpleadoAusencia.id_ausencia != excluir_id)
        ausencias = query.all()
        reservadas = sum(
            calcular_dias_ausencia_en_rango(
                ausencia,
                inicio_anio,
                fin_anio,
                feriados_por_anio=feriados_por_anio,
            )
            for ausencia in ausencias
        )
        usadas = sum(
            calcular_dias_ausencia_en_rango(
                ausencia,
                inicio_anio,
                fin_anio,
                feriados_por_anio=feriados_por_anio,
            )
            for ausencia in ausencias
            if ausencia.estado in ESTADOS_AUSENCIA_CONFIRMADOS
        )
        cupo = empleado.dias_vacaciones_anuales_int()
        saldos[anio] = {
            'cupo': cupo,
            'reservadas': reservadas,
            'usadas': usadas,
            'disponibles': max(cupo - reservadas, 0),
        }
    return saldos


def construir_segmentos_vacaciones(
    fecha_desde: date,
    fecha_hasta: date,
    disponibles_por_anio: dict[int, int],
    feriados_por_anio: dict[int, set[date]] | None = None,
    tipo_excedente: str | None = None,
) -> tuple[list[dict], int]:
    segmentos: list[dict] = []
    overflow = 0
    actual = fecha_desde

    while actual <= fecha_hasta:
        disponible = disponibles_por_anio.get(actual.year, 0)
        dia_habil = es_dia_habil_vacaciones(actual, feriados_por_anio=feriados_por_anio)
        tipo = 'vacaciones' if disponible > 0 else (tipo_excedente or '')
        if tipo == 'vacaciones' and dia_habil:
            disponibles_por_anio[actual.year] = disponible - 1
        elif tipo != 'vacaciones' and dia_habil:
            overflow += 1

        if segmentos and segmentos[-1]['tipo'] == tipo and segmentos[-1]['fecha_hasta'] == actual - timedelta(days=1):
            segmentos[-1]['fecha_hasta'] = actual
        else:
            segmentos.append({
                'tipo': tipo,
                'fecha_desde': actual,
                'fecha_hasta': actual,
            })
        actual += timedelta(days=1)

    return segmentos, overflow


def encontrar_ausencia_solapada(
    empleado: Empleado,
    fecha_desde: date,
    fecha_hasta: date,
    excluir_id: int | None = None,
) -> EmpleadoAusencia | None:
    query = empleado.ausencias.filter(
        EmpleadoAusencia.estado.in_(tuple(ESTADOS_AUSENCIA_BLOQUEAN_SOLAPE)),
        EmpleadoAusencia.fecha_desde <= fecha_hasta,
        EmpleadoAusencia.fecha_hasta >= fecha_desde,
    )
    if excluir_id:
        query = query.filter(EmpleadoAusencia.id_ausencia != excluir_id)
    return query.order_by(
        EmpleadoAusencia.fecha_desde.asc(),
        EmpleadoAusencia.id_ausencia.asc(),
    ).first()


def construir_panel_ausencias(
    empleado: Empleado,
    filtros: dict,
    cliente_id: int | None = None,
    per_page: int = 10,
) -> dict:
    anio = int(filtros['anio'])
    inicio_anio = date(anio, 1, 1)
    fin_anio = date(anio, 12, 31)
    feriados_por_anio = construir_calendario_feriados([anio], cliente_id=cliente_id)

    query_anual = empleado.ausencias.filter(
        EmpleadoAusencia.fecha_desde <= fin_anio,
        EmpleadoAusencia.fecha_hasta >= inicio_anio,
    )
    ausencias_anuales = query_anual.order_by(
        EmpleadoAusencia.fecha_desde.desc(),
        EmpleadoAusencia.id_ausencia.desc(),
    ).all()

    query_tabla = query_anual
    if filtros['tipo']:
        query_tabla = query_tabla.filter(EmpleadoAusencia.tipo == filtros['tipo'])
    if filtros['estado']:
        query_tabla = query_tabla.filter(EmpleadoAusencia.estado == filtros['estado'])

    paginacion = query_tabla.order_by(
        EmpleadoAusencia.fecha_desde.desc(),
        EmpleadoAusencia.id_ausencia.desc(),
    ).paginate(page=filtros['page'], per_page=per_page, error_out=False)
    dias_computados = {
        ausencia.id_ausencia: calcular_dias_ausencia_en_rango(
            ausencia,
            ausencia.fecha_desde,
            ausencia.fecha_hasta,
            feriados_por_anio=feriados_por_anio,
        )
        for ausencia in paginacion.items
    }

    vacaciones_usadas = sum(
        calcular_dias_ausencia_en_rango(
            ausencia,
            inicio_anio,
            fin_anio,
            feriados_por_anio=feriados_por_anio,
        )
        for ausencia in ausencias_anuales
        if ausencia.tipo == 'vacaciones' and ausencia.estado in ESTADOS_AUSENCIA_CONFIRMADOS
    )
    vacaciones_reservadas = sum(
        calcular_dias_ausencia_en_rango(
            ausencia,
            inicio_anio,
            fin_anio,
            feriados_por_anio=feriados_por_anio,
        )
        for ausencia in ausencias_anuales
        if ausencia.tipo == 'vacaciones' and ausencia.estado in ESTADOS_AUSENCIA_RESERVAN_VACACIONES
    )
    dias_libres_usados = sum(
        calcular_dias_ausencia_en_rango(
            ausencia,
            inicio_anio,
            fin_anio,
            feriados_por_anio=feriados_por_anio,
        )
        for ausencia in ausencias_anuales
        if ausencia.tipo == 'dia_libre' and ausencia.estado in ESTADOS_AUSENCIA_CONFIRMADOS
    )
    feriados_query = EmpleadoFeriado.query.filter(
        EmpleadoFeriado.fecha >= inicio_anio,
        EmpleadoFeriado.fecha <= fin_anio,
    )
    if cliente_id:
        feriados_query = feriados_query.filter(EmpleadoFeriado.cliente_id == cliente_id)
    else:
        feriados_query = feriados_query.filter(EmpleadoFeriado.cliente_id.is_(None))
    feriados_personalizados = feriados_query.order_by(
        EmpleadoFeriado.fecha.asc(),
        EmpleadoFeriado.id_feriado.asc(),
    ).all()
    solicitudes_pendientes = sum(1 for ausencia in ausencias_anuales if ausencia.estado == 'pendiente')
    proxima_ausencia = empleado.ausencias.filter(
        EmpleadoAusencia.estado.in_(tuple(ESTADOS_AUSENCIA_CONFIRMADOS)),
        EmpleadoAusencia.fecha_hasta >= date.today(),
    ).order_by(
        EmpleadoAusencia.fecha_desde.asc(),
        EmpleadoAusencia.id_ausencia.asc(),
    ).first()

    anio_actual = date.today().year
    anio_ingreso = empleado.fecha_ingreso.year if empleado.fecha_ingreso else anio_actual
    anio_inicial = min(anio_ingreso, anio, anio_actual)
    anio_final = max(anio, anio_actual)
    opciones_anio = list(range(anio_final + 1, anio_inicial - 1, -1))

    return {
        'filtros': filtros,
        'paginacion': paginacion,
        'dias_computados': dias_computados,
        'saldo_vacaciones': max(empleado.dias_vacaciones_anuales_int() - vacaciones_reservadas, 0),
        'vacaciones_usadas': vacaciones_usadas,
        'vacaciones_reservadas': vacaciones_reservadas,
        'dias_libres_usados': dias_libres_usados,
        'feriados_personalizados': feriados_personalizados,
        'solicitudes_pendientes': solicitudes_pendientes,
        'proxima_ausencia': proxima_ausencia,
        'opciones_anio': opciones_anio,
    }
