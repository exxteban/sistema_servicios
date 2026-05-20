"""Servicio de asistencia diaria (lunes-domingo) para el módulo de empleados.

Calcula el descuento por días no trabajados o medio día, basándose en el
valor diario del sueldo base (sueldo ÷ días del mes).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from control_de_empleados.models import (
    ESTADO_ASISTENCIA_AUSENTE,
    ESTADO_ASISTENCIA_FERIADO,
    ESTADO_ASISTENCIA_MEDIO_DIA,
    ESTADO_ASISTENCIA_PRESENTE,
    EmpleadoAsistenciaDia,
)

DECIMAL_CENTS = Decimal('0.01')
MEDIO_DIA_FACTOR = Decimal('0.5')

ETIQUETAS_ESTADO = {
    ESTADO_ASISTENCIA_PRESENTE: 'Vino',
    ESTADO_ASISTENCIA_AUSENTE: 'No vino',
    ESTADO_ASISTENCIA_MEDIO_DIA: 'Medio día',
    ESTADO_ASISTENCIA_FERIADO: 'Feriado',
}

NOMBRES_DIA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


@dataclass
class DiaAsistencia:
    fecha: date
    nombre_dia: str
    estado: str
    observaciones: str | None
    id_asistencia: int | None
    es_domingo: bool
    valor_dia: Decimal
    descuento: Decimal


@dataclass
class SemanaAsistencia:
    numero_semana: int
    dias: list[DiaAsistencia] = field(default_factory=list)


@dataclass
class ResumenAsistencia:
    periodo: str
    dias_mes: int
    valor_dia: Decimal
    dias_presentes: int
    dias_ausentes: int
    dias_medio: int
    dias_feriado: int
    dias_sin_registro: int
    descuento_total: Decimal
    semanas: list[SemanaAsistencia]


def _quantize(valor: Decimal) -> Decimal:
    return valor.quantize(DECIMAL_CENTS)


def _valor_dia(salario_base: Decimal, dias_mes: int) -> Decimal:
    if dias_mes <= 0:
        return Decimal('0.00')
    return _quantize(salario_base / Decimal(dias_mes))


def _descuento_por_estado(estado: str, valor_dia: Decimal) -> Decimal:
    if estado == ESTADO_ASISTENCIA_AUSENTE:
        return _quantize(valor_dia)
    if estado == ESTADO_ASISTENCIA_MEDIO_DIA:
        return _quantize(valor_dia * MEDIO_DIA_FACTOR)
    return Decimal('0.00')


def _dias_del_periodo(periodo: str) -> list[date]:
    """Devuelve todos los días del mes del período dado (YYYY-MM)."""
    try:
        anio, mes = int(periodo[:4]), int(periodo[5:7])
    except (ValueError, IndexError):
        hoy = date.today()
        anio, mes = hoy.year, hoy.month
    total_dias = calendar.monthrange(anio, mes)[1]
    return [date(anio, mes, d) for d in range(1, total_dias + 1)]


def _agrupar_en_semanas(dias: list[DiaAsistencia]) -> list[SemanaAsistencia]:
    """Agrupa los días en semanas lunes-domingo."""
    semanas: list[SemanaAsistencia] = []
    semana_actual: SemanaAsistencia | None = None
    num_semana = 0

    for dia in dias:
        # weekday(): 0=lunes, 6=domingo
        if dia.fecha.weekday() == 0 or semana_actual is None:
            num_semana += 1
            semana_actual = SemanaAsistencia(numero_semana=num_semana)
            semanas.append(semana_actual)
        semana_actual.dias.append(dia)

    return semanas


def construir_panel_asistencia(
    empleado,
    periodo: str,
) -> ResumenAsistencia:
    """Construye el panel completo de asistencia para un empleado y período."""
    dias_calendario = _dias_del_periodo(periodo)
    dias_mes = len(dias_calendario)
    salario_base = empleado.salario_base_decimal()
    vd = _valor_dia(salario_base, dias_mes)

    # Cargar registros existentes indexados por fecha
    registros = EmpleadoAsistenciaDia.query.filter(
        EmpleadoAsistenciaDia.id_empleado == empleado.id_empleado,
        EmpleadoAsistenciaDia.periodo == periodo,
    ).all()
    por_fecha: dict[date, EmpleadoAsistenciaDia] = {r.fecha: r for r in registros}

    dias_presentes = dias_ausentes = dias_medio = dias_feriado = dias_sin_registro = 0
    descuento_total = Decimal('0.00')
    dias_asistencia: list[DiaAsistencia] = []

    for fecha in dias_calendario:
        registro = por_fecha.get(fecha)
        if registro:
            estado = registro.estado
            obs = registro.observaciones
            id_reg = registro.id_asistencia
        else:
            estado = ESTADO_ASISTENCIA_PRESENTE  # default visual: presente
            obs = None
            id_reg = None
            dias_sin_registro += 1

        descuento = _descuento_por_estado(estado, vd)
        descuento_total += descuento

        if registro:
            if estado == ESTADO_ASISTENCIA_PRESENTE:
                dias_presentes += 1
            elif estado == ESTADO_ASISTENCIA_AUSENTE:
                dias_ausentes += 1
            elif estado == ESTADO_ASISTENCIA_MEDIO_DIA:
                dias_medio += 1
            elif estado == ESTADO_ASISTENCIA_FERIADO:
                dias_feriado += 1

        dias_asistencia.append(DiaAsistencia(
            fecha=fecha,
            nombre_dia=NOMBRES_DIA[fecha.weekday()],
            estado=estado,
            observaciones=obs,
            id_asistencia=id_reg,
            es_domingo=fecha.weekday() == 6,
            valor_dia=vd,
            descuento=descuento,
        ))

    semanas = _agrupar_en_semanas(dias_asistencia)

    return ResumenAsistencia(
        periodo=periodo,
        dias_mes=dias_mes,
        valor_dia=vd,
        dias_presentes=dias_presentes,
        dias_ausentes=dias_ausentes,
        dias_medio=dias_medio,
        dias_feriado=dias_feriado,
        dias_sin_registro=dias_sin_registro,
        descuento_total=_quantize(descuento_total),
        semanas=semanas,
    )


def calcular_descuento_asistencia(id_empleado: int, periodo: str, salario_base: Decimal) -> Decimal:
    """Calcula el descuento total por asistencia para usar en el resumen salarial."""
    registros = EmpleadoAsistenciaDia.query.filter(
        EmpleadoAsistenciaDia.id_empleado == id_empleado,
        EmpleadoAsistenciaDia.periodo == periodo,
    ).all()
    if not registros:
        return Decimal('0.00')

    dias_calendario = _dias_del_periodo(periodo)
    dias_mes = len(dias_calendario)
    vd = _valor_dia(salario_base, dias_mes)

    total = Decimal('0.00')
    for r in registros:
        total += _descuento_por_estado(r.estado, vd)
    return _quantize(total)
