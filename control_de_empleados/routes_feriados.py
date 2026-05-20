from datetime import date

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.utils.auditoria_utils import registrar_auditoria
from control_de_empleados.models import EmpleadoFeriado
from control_de_empleados.routes import (
    _aplicar_scope_cliente,
    _obtener_cliente_scope,
    _parse_fecha,
    _resolver_denegacion,
    control_empleados_bp,
)
from control_de_empleados.services.filtros import normalizar_periodo


def _url_feriados(anio: int) -> str:
    return url_for('control_empleados.feriados', anio=anio)


@control_empleados_bp.route('/feriados', methods=['GET', 'POST'])
@login_required
def feriados():
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    anio = request.args.get('anio', date.today().year, type=int)
    if request.method == 'POST':
        anio = request.form.get('anio', date.today().year, type=int)
        fecha = _parse_fecha(request.form.get('fecha'))
        motivo = (request.form.get('motivo') or '').strip()
        cliente_scope = _obtener_cliente_scope()
        if fecha is None or not motivo:
            flash('Completa fecha y motivo del feriado.', 'warning')
            return redirect(_url_feriados(anio))

        existente = EmpleadoFeriado.query.filter_by(
            cliente_id=cliente_scope,
            fecha=fecha,
        ).first()
        if existente:
            flash('Ya existe un feriado personalizado para esa fecha.', 'warning')
            return redirect(_url_feriados(anio))

        feriado = EmpleadoFeriado(
            cliente_id=cliente_scope,
            fecha=fecha,
            motivo=motivo,
        )
        db.session.add(feriado)
        db.session.flush()

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='crear_feriado_personalizado',
                    modulo='control_empleados',
                    descripcion=f'Registró feriado personalizado {fecha.isoformat()}',
                    referencia_tipo='empleado_feriado',
                    referencia_id=feriado.id_feriado,
                    datos_nuevos={
                        'cliente_id': cliente_scope,
                        'fecha': fecha.isoformat(),
                        'motivo': motivo,
                    },
                    commit=False,
                )
        except Exception:
            pass

        db.session.commit()
        flash('Feriado personalizado guardado. Ya impacta en el cálculo de vacaciones.', 'success')
        return redirect(_url_feriados(fecha.year))

    cliente_scope = _obtener_cliente_scope()
    inicio_anio = date(anio, 1, 1)
    fin_anio = date(anio, 12, 31)
    query = EmpleadoFeriado.query.filter(
        EmpleadoFeriado.fecha >= inicio_anio,
        EmpleadoFeriado.fecha <= fin_anio,
    )
    if cliente_scope:
        query = query.filter(EmpleadoFeriado.cliente_id == cliente_scope)
    else:
        query = query.filter(EmpleadoFeriado.cliente_id.is_(None))
    feriados = query.order_by(
        EmpleadoFeriado.fecha.asc(),
        EmpleadoFeriado.id_feriado.asc(),
    ).all()
    opciones_anio = list(range(date.today().year + 1, date.today().year - 6, -1))
    return render_template(
        'control_de_empleados/feriados.html',
        anio=anio,
        feriados=feriados,
        opciones_anio=opciones_anio,
        fecha_hoy=date.today().isoformat(),
        periodo_actual=normalizar_periodo(None),
    )


@control_empleados_bp.route('/feriados/<int:id_feriado>/eliminar', methods=['POST'])
@login_required
def eliminar_feriado(id_feriado: int):
    denegacion = _resolver_denegacion('gestionar_control_empleados')
    if denegacion:
        return denegacion

    feriado = _aplicar_scope_cliente(
        EmpleadoFeriado.query,
        EmpleadoFeriado,
    ).filter(
        EmpleadoFeriado.id_feriado == id_feriado,
    ).first_or_404()

    anio = feriado.fecha.year
    try:
        with db.session.begin_nested():
            registrar_auditoria(
                accion='eliminar_feriado_personalizado',
                modulo='control_empleados',
                descripcion=f'Eliminó feriado personalizado {feriado.fecha.isoformat()}',
                referencia_tipo='empleado_feriado',
                referencia_id=feriado.id_feriado,
                datos_anteriores={
                    'cliente_id': feriado.cliente_id,
                    'fecha': feriado.fecha.isoformat(),
                    'motivo': feriado.motivo,
                },
                commit=False,
            )
    except Exception:
        pass

    db.session.delete(feriado)
    db.session.commit()
    flash('Feriado personalizado eliminado.', 'success')
    return redirect(_url_feriados(anio))
