from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from control_de_empleados.models import (
    Empleado,
    EmpleadoMovimientoSalario,
    EmpleadoPago,
)

AGUINALDO_DIVISOR = Decimal('12')
DECIMAL_CENTS = Decimal('0.01')


@dataclass(frozen=True)
class CortePeriodo:
    fecha_corte: date
    fecha_proyeccion: date
    anio: int
    mes: int
    es_mes_actual: bool


def _quantize(valor: Decimal) -> Decimal:
    return valor.quantize(DECIMAL_CENTS)


def _inicio_mes(anio: int, mes: int) -> date:
    return date(anio, mes, 1)


def _fin_mes(anio: int, mes: int) -> date:
    return date(anio, mes, monthrange(anio, mes)[1])


def _resolver_corte(periodo: str, hoy: date | None = None) -> CortePeriodo:
    fecha_hoy = hoy or date.today()
    try:
        anio, mes = [int(parte) for parte in periodo.split('-', 1)]
    except (TypeError, ValueError):
        anio, mes = fecha_hoy.year, fecha_hoy.month
    if mes < 1 or mes > 12:
        anio, mes = fecha_hoy.year, fecha_hoy.month
    fin_mes = _fin_mes(anio, mes)
    es_mes_actual = anio == fecha_hoy.year and mes == fecha_hoy.month
    fecha_corte = fecha_hoy if es_mes_actual else fin_mes
    return CortePeriodo(
        fecha_corte=min(fecha_corte, fin_mes),
        fecha_proyeccion=date(anio, 12, 31),
        anio=anio,
        mes=mes,
        es_mes_actual=es_mes_actual,
    )


def _dias_inclusivos(desde: date, hasta: date) -> int:
    if hasta < desde:
        return 0
    return (hasta - desde).days + 1


def _limites_empleo(empleado: Empleado) -> tuple[date | None, date | None]:
    return empleado.fecha_ingreso, empleado.fecha_egreso


def _dias_trabajados_en_intervalo(
    empleado: Empleado,
    desde: date,
    hasta: date,
) -> tuple[int, date | None, date | None]:
    fecha_ingreso, fecha_egreso = _limites_empleo(empleado)
    inicio_real = max(desde, fecha_ingreso) if fecha_ingreso else desde
    fin_real = min(hasta, fecha_egreso) if fecha_egreso else hasta
    dias = _dias_inclusivos(inicio_real, fin_real)
    if dias <= 0:
        return 0, None, None
    return dias, inicio_real, fin_real


def _sumar_extras_remunerativos(movimientos: list[EmpleadoMovimientoSalario]) -> Decimal:
    total = Decimal('0.00')
    for movimiento in movimientos:
        if movimiento.incide_aguinaldo_bool():
            total += movimiento.monto_decimal()
    return _quantize(total)


def _construir_indice_periodo(registros: list, atributo_periodo: str) -> dict[str, list]:
    indice: dict[str, list] = {}
    for registro in registros:
        clave = getattr(registro, atributo_periodo)
        indice.setdefault(clave, []).append(registro)
    return indice


def _remuneracion_mensual(
    empleado: Empleado,
    periodo: str,
    pagos_por_periodo: dict[str, list[EmpleadoPago]],
    movimientos_por_periodo: dict[str, list[EmpleadoMovimientoSalario]],
) -> tuple[Decimal, str]:
    pagos = pagos_por_periodo.get(periodo) or []
    movimientos = movimientos_por_periodo.get(periodo) or []
    extras_aguinaldo = _sumar_extras_remunerativos(movimientos)
    if pagos:
        pago = pagos[0]
        remuneracion = pago.salario_base_decimal() + extras_aguinaldo
        return _quantize(remuneracion), 'pago_registrado'

    remuneracion = empleado.salario_base_decimal() + extras_aguinaldo
    return _quantize(remuneracion), 'estimado'


def calcular_resumen_aguinaldo(
    empleado: Empleado,
    periodo: str,
    hoy: date | None = None,
) -> dict:
    corte = _resolver_corte(periodo, hoy=hoy)
    periodo_inicio = f'{corte.anio}-01'
    periodo_fin = f'{corte.anio}-12'

    pagos = EmpleadoPago.query.filter(
        EmpleadoPago.id_empleado == empleado.id_empleado,
        EmpleadoPago.periodo >= periodo_inicio,
        EmpleadoPago.periodo <= periodo_fin,
    ).order_by(EmpleadoPago.periodo.asc(), EmpleadoPago.id_pago.asc()).all()
    movimientos = EmpleadoMovimientoSalario.query.filter(
        EmpleadoMovimientoSalario.id_empleado == empleado.id_empleado,
        EmpleadoMovimientoSalario.periodo >= periodo_inicio,
        EmpleadoMovimientoSalario.periodo <= periodo_fin,
    ).order_by(
        EmpleadoMovimientoSalario.periodo.asc(),
        EmpleadoMovimientoSalario.id_movimiento.asc(),
    ).all()

    pagos_por_periodo = _construir_indice_periodo(pagos, 'periodo')
    movimientos_por_periodo = _construir_indice_periodo(movimientos, 'periodo')

    meses = []
    remuneracion_acumulada = Decimal('0.00')
    aguinaldo_acumulado = Decimal('0.00')
    remuneracion_proyectada = Decimal('0.00')
    aguinaldo_proyectado = Decimal('0.00')
    tasa_diaria_actual = Decimal('0.00')
    aguinaldo_mes_actual = Decimal('0.00')
    aguinaldo_mes_completo = Decimal('0.00')

    for mes in range(1, 13):
        inicio_mes = _inicio_mes(corte.anio, mes)
        fin_mes = _fin_mes(corte.anio, mes)
        periodo_mes = inicio_mes.strftime('%Y-%m')
        dias_mes = monthrange(corte.anio, mes)[1]
        remuneracion_mes, fuente = _remuneracion_mensual(
            empleado,
            periodo_mes,
            pagos_por_periodo,
            movimientos_por_periodo,
        )
        dias_laborados_mes, _, _ = _dias_trabajados_en_intervalo(empleado, inicio_mes, fin_mes)
        proporcion_mes = (
            Decimal(dias_laborados_mes) / Decimal(dias_mes)
            if dias_laborados_mes
            else Decimal('0.00')
        )
        remuneracion_proyectada_mes = _quantize(remuneracion_mes * proporcion_mes)
        aguinaldo_mes_proyectado = _quantize(remuneracion_proyectada_mes / AGUINALDO_DIVISOR)
        remuneracion_proyectada += remuneracion_proyectada_mes
        aguinaldo_proyectado += aguinaldo_mes_proyectado

        fin_acumulado_mes = min(fin_mes, corte.fecha_corte)
        dias_acumulados_mes, _, _ = _dias_trabajados_en_intervalo(
            empleado,
            inicio_mes,
            fin_acumulado_mes,
        )
        proporcion_acumulada = (
            Decimal(dias_acumulados_mes) / Decimal(dias_mes)
            if dias_acumulados_mes
            else Decimal('0.00')
        )
        remuneracion_acumulada_mes = _quantize(remuneracion_mes * proporcion_acumulada)
        aguinaldo_acumulado_mes = _quantize(remuneracion_acumulada_mes / AGUINALDO_DIVISOR)

        if mes <= corte.mes:
            remuneracion_acumulada += remuneracion_acumulada_mes
            aguinaldo_acumulado += aguinaldo_acumulado_mes

        if mes == corte.mes:
            tasa_diaria_actual = (
                _quantize((remuneracion_mes / AGUINALDO_DIVISOR) / Decimal(dias_mes))
                if dias_mes
                else Decimal('0.00')
            )
            aguinaldo_mes_actual = aguinaldo_acumulado_mes
            aguinaldo_mes_completo = aguinaldo_mes_proyectado

        meses.append({
            'periodo': periodo_mes,
            'label': inicio_mes.strftime('%m/%Y'),
            'dias_mes': dias_mes,
            'dias_computados': dias_acumulados_mes if mes <= corte.mes else 0,
            'dias_proyectados': dias_laborados_mes,
            'remuneracion_mes': remuneracion_mes,
            'remuneracion_acumulada_mes': remuneracion_acumulada_mes,
            'remuneracion_proyectada_mes': remuneracion_proyectada_mes,
            'aguinaldo_acumulado_mes': aguinaldo_acumulado_mes,
            'aguinaldo_proyectado_mes': aguinaldo_mes_proyectado,
            'fuente': fuente,
        })

    salario_base = empleado.salario_base_decimal()
    ips_obrero = empleado.ips_obrero_estimado_decimal()
    salario_neto = empleado.salario_neto_estimado_decimal()

    return {
        'anio': corte.anio,
        'fecha_corte': corte.fecha_corte,
        'fecha_proyeccion': corte.fecha_proyeccion,
        'mes_actual': corte.mes,
        'es_mes_actual': corte.es_mes_actual,
        'aguinaldo_acumulado': _quantize(aguinaldo_acumulado),
        'aguinaldo_proyectado': _quantize(aguinaldo_proyectado),
        'aguinaldo_mes_actual': _quantize(aguinaldo_mes_actual),
        'aguinaldo_mes_completo': _quantize(aguinaldo_mes_completo),
        'tasa_diaria_actual': _quantize(tasa_diaria_actual),
        'remuneracion_acumulada': _quantize(remuneracion_acumulada),
        'remuneracion_proyectada': _quantize(remuneracion_proyectada),
        'salario_base': salario_base,
        'salario_incluye_ips': bool(empleado.salario_incluye_ips),
        'ips_obrero_estimado': ips_obrero,
        'salario_neto_estimado': salario_neto,
        'meses': meses,
        'usa_fecha_egreso': empleado.fecha_egreso is not None,
    }
