"""Rutas para el tab de asistencia diaria (lunes-domingo) del módulo de empleados."""
from __future__ import annotations

from datetime import datetime

from flask import flash, redirect, request, url_for
from flask_login import login_required

from app import db
from control_de_empleados.models import (
    ESTADOS_ASISTENCIA_VALIDOS,
    EmpleadoAsistenciaDia,
)
from control_de_empleados.routes import (
    _cliente_id_para_nuevo_registro,
    _obtener_empleado_o_404,
    _parse_fecha,
    _resolver_denegacion,
    control_empleados_bp,
)
from control_de_empleados.services.filtros import normalizar_periodo


def _url_asistencia(id_empleado: int, periodo: str) -> str:
    return url_for(
        'control_empleados.detalle',
        id_empleado=id_empleado,
        periodo=periodo,
        tab='asistencia',
    )


@control_empleados_bp.route('/<int:id_empleado>/asistencia/guardar', methods=['POST'])
@login_required
def guardar_asistencia(id_empleado: int):
    """Guarda o actualiza el estado de asistencia de un día específico."""
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    periodo = normalizar_periodo(request.form.get('periodo'))
    fecha = _parse_fecha(request.form.get('fecha'))
    estado = (request.form.get('estado') or '').strip().lower()
    observaciones = (request.form.get('observaciones') or '').strip() or None

    if fecha is None:
        flash('Fecha inválida.', 'warning')
        return redirect(_url_asistencia(id_empleado, periodo))

    if estado not in ESTADOS_ASISTENCIA_VALIDOS:
        flash('Estado de asistencia inválido.', 'warning')
        return redirect(_url_asistencia(id_empleado, periodo))

    # Verificar que la fecha pertenece al período
    fecha_periodo = fecha.strftime('%Y-%m')
    if fecha_periodo != periodo:
        flash('La fecha no corresponde al período seleccionado.', 'warning')
        return redirect(_url_asistencia(id_empleado, periodo))

    registro = EmpleadoAsistenciaDia.query.filter_by(
        id_empleado=empleado.id_empleado,
        fecha=fecha,
    ).first()

    if registro:
        registro.estado = estado
        registro.observaciones = observaciones
        registro.fecha_modificacion = datetime.utcnow()
    else:
        registro = EmpleadoAsistenciaDia(
            cliente_id=_cliente_id_para_nuevo_registro(empleado),
            id_empleado=empleado.id_empleado,
            periodo=periodo,
            fecha=fecha,
            estado=estado,
            observaciones=observaciones,
        )
        db.session.add(registro)

    db.session.commit()
    return redirect(_url_asistencia(id_empleado, periodo))


@control_empleados_bp.route('/<int:id_empleado>/asistencia/guardar-semana', methods=['POST'])
@login_required
def guardar_semana_asistencia(id_empleado: int):
    """Guarda todos los días de una semana de una sola vez (submit del formulario semanal)."""
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    empleado = _obtener_empleado_o_404(id_empleado)
    periodo = normalizar_periodo(request.form.get('periodo'))
    cliente_id = _cliente_id_para_nuevo_registro(empleado)

    # El formulario envía campos con nombre "estado_YYYY-MM-DD"
    errores = 0
    guardados = 0
    for key, valor in request.form.items():
        if not key.startswith('estado_'):
            continue
        fecha_str = key[len('estado_'):]
        fecha = _parse_fecha(fecha_str)
        if fecha is None:
            continue
        if fecha.strftime('%Y-%m') != periodo:
            continue
        estado = valor.strip().lower()
        if estado not in ESTADOS_ASISTENCIA_VALIDOS:
            errores += 1
            continue
        obs_key = f'obs_{fecha_str}'
        observaciones = (request.form.get(obs_key) or '').strip() or None

        registro = EmpleadoAsistenciaDia.query.filter_by(
            id_empleado=empleado.id_empleado,
            fecha=fecha,
        ).first()
        if registro:
            registro.estado = estado
            registro.observaciones = observaciones
            registro.fecha_modificacion = datetime.utcnow()
        else:
            db.session.add(EmpleadoAsistenciaDia(
                cliente_id=cliente_id,
                id_empleado=empleado.id_empleado,
                periodo=periodo,
                fecha=fecha,
                estado=estado,
                observaciones=observaciones,
            ))
        guardados += 1

    if guardados > 0:
        db.session.commit()
        flash(f'Asistencia guardada: {guardados} día(s) actualizados.', 'success')
    if errores > 0:
        flash(f'{errores} día(s) con estado inválido fueron ignorados.', 'warning')

    return redirect(_url_asistencia(id_empleado, periodo))
