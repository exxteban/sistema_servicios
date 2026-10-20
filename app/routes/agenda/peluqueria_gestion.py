from datetime import timedelta

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.routes.agenda import agenda_bp
from app.routes.agenda.actividades import _parse_datetime_local
from app.routes.agenda.peluqueria import (
    _append_turno_note,
    _build_turno_redirect_pos_params,
    _buscar_turno_solapado,
    _cargar_turno_peluqueria_visible_o_404,
    _duracion_minutos_actividad,
    _parse_positive_int,
    _redirect_gestion_turno,
    _to_date_input,
    _to_time_input,
)
from app.services.agenda_turnos_peluqueria import parse_turno_manual_price, resolve_turno_peluqueria_catalog_service
from app.services.peluqueria_senas import registrar_sena_turno, resolver_sena_al_cerrar, sena_turno, turno_ya_cobrado
from app.services.peluqueria_turno_estado import (
    AGENDADO,
    CANCELADO,
    COBRADO,
    EN_ATENCION,
    ETIQUETAS,
    NO_SHOW,
    PASOS,
    TERMINADO,
    empezar_atencion,
    enlace_whatsapp_turno,
    estado_turno,
    terminar_turno,
)


def _puede_atender():
    return current_user.tiene_permiso('agenda_editar') or current_user.tiene_permiso('agenda_completar')


def url_cobro_turno(actividad):
    """POS con el turno, su seña y el profesional como vendedor; None si ya está cobrado."""
    if turno_ya_cobrado(actividad):
        return None
    if actividad.cliente_servicio_id:
        return url_for('ventas.pos', cliente_servicio_id=int(actividad.cliente_servicio_id))
    # Turnos anteriores a guardar servicio_id: mismo criterio por título que Cobros pendientes.
    servicio = resolve_turno_peluqueria_catalog_service(servicio_id=actividad.servicio_id, title=actividad.titulo)
    params = _build_turno_redirect_pos_params(
        cliente_id=actividad.cliente_id,
        servicio_catalogo_id=(servicio.id_servicio if servicio else None),
        profesional_id=actividad.usuario_id,
        manual_price=actividad.precio_manual,
        title=(actividad.titulo if servicio is None else None),
        price_option_id=actividad.servicio_precio_opcion_id,
        actividad_id=actividad.id,
    )
    return url_for('ventas.pos', **params)


def _render_gestion(actividad):
    estado = estado_turno(actividad)
    return render_template(
        'agenda/peluqueria_gestionar_turno.html',
        actividad=actividad,
        estado=estado,
        estado_label=ETIQUETAS[estado],
        pasos=[(paso, ETIQUETAS[paso]) for paso in PASOS],
        indice_actual=(PASOS.index(estado) if estado in PASOS else -1),
        cerrado=estado in {CANCELADO, NO_SHOW},
        puede_empezar=(estado == AGENDADO and _puede_atender()),
        puede_terminar=(estado in {AGENDADO, EN_ATENCION} and current_user.tiene_permiso('agenda_completar')),
        url_cobro=(url_cobro_turno(actividad) if estado in {AGENDADO, EN_ATENCION, TERMINADO} and current_user.tiene_permiso('crear_venta') else None),
        whatsapp_confirmar=enlace_whatsapp_turno(actividad, 'confirmacion'),
        whatsapp_recordar=enlace_whatsapp_turno(actividad, 'recordatorio'),
        fecha_actual=_to_date_input(actividad.fecha_inicio),
        hora_actual=_to_time_input(actividad.fecha_inicio),
        duracion_actual=_duracion_minutos_actividad(actividad),
        puede_reprogramar=current_user.tiene_permiso('agenda_editar') and estado in {AGENDADO, CANCELADO, NO_SHOW},
        puede_cancelar=current_user.tiene_permiso('agenda_cancelar'),
        puede_registrar_sena=(current_user.tiene_permiso('agenda_editar') or current_user.tiene_permiso('crear_venta')),
        sena_actual=float(sena_turno(actividad)),
        turno_cobrado=(estado == COBRADO),
    )


def _reprogramar(actividad):
    if not current_user.tiene_permiso('agenda_editar'):
        return 'No tienes permiso para reprogramar turnos.'
    if estado_turno(actividad) in {EN_ATENCION, TERMINADO, COBRADO}:
        return 'Este turno ya está en atención o atendido: no se puede reprogramar.'
    fecha_inicio = _parse_datetime_local(f"{request.form.get('fecha') or ''}T{request.form.get('hora') or ''}")
    duracion = _parse_positive_int(request.form.get('duracion')) or _duracion_minutos_actividad(actividad)
    if fecha_inicio is None:
        return 'Completa una fecha y hora validas para reprogramar.'
    fecha_fin = fecha_inicio + timedelta(minutes=duracion)
    if _buscar_turno_solapado(profesional_id=actividad.usuario_id, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, excluir_actividad_id=actividad.id):
        return 'Ese profesional ya tiene otro turno en ese horario.'
    actividad.fecha_inicio = fecha_inicio
    actividad.fecha_fin = fecha_fin
    actividad.estado = 'pendiente'
    actividad.cierre_motivo = None
    actividad.recordatorio_whatsapp_at = None
    if actividad.cliente_servicio is not None:
        actividad.cliente_servicio.fecha_programada = fecha_inicio
        if (actividad.cliente_servicio.estado or '').strip().lower() in {'solicitado', 'presupuestado', 'cancelado'}:
            actividad.cliente_servicio.estado = 'agendado'
            actividad.cliente_servicio.fecha_cierre = None
    flash('Turno reprogramado correctamente.', 'success')
    return None


def _registrar_sena(actividad):
    if not (current_user.tiene_permiso('agenda_editar') or current_user.tiene_permiso('crear_venta')):
        return 'No tienes permiso para registrar señas.'
    monto = parse_turno_manual_price(request.form.get('monto_sena'))
    ok, error = registrar_sena_turno(actividad, monto, current_user, request.form.get('nota_sena'))
    if not ok:
        return error
    flash('Seña registrada: entró a tu caja y se descuenta al cobrar el turno.', 'success')
    return None


def _cerrar(actividad, accion):
    if not current_user.tiene_permiso('agenda_cancelar'):
        return 'No tienes permiso para cerrar turnos.'
    if turno_ya_cobrado(actividad):
        return 'Este turno ya fue cobrado; no se puede cancelar desde acá.'
    if estado_turno(actividad) in {TERMINADO, CANCELADO, NO_SHOW}:
        return 'Este turno ya está cerrado.'
    ok, error = resolver_sena_al_cerrar(actividad, current_user, devolver=request.form.get('devolver_sena') == '1')
    if not ok:
        return error
    motivo = (request.form.get('motivo') or '').strip()
    etiqueta = 'No-show' if accion == 'no_show' else 'Cancelado'
    actividad.estado = 'cancelada'
    actividad.cierre_motivo = NO_SHOW if accion == 'no_show' else CANCELADO
    if actividad.cliente_servicio is not None and not actividad.cliente_servicio.id_venta:
        actividad.cliente_servicio.estado = 'cancelado'
    _append_turno_note(actividad, f'{etiqueta} desde peluquería/barbería' + (f': {motivo}' if motivo else '.'))
    flash('Turno marcado como no-show.' if accion == 'no_show' else 'Turno cancelado correctamente.', 'success')
    return None


def _empezar(actividad):
    if not _puede_atender():
        return 'No tienes permiso para empezar la atención.'
    error = empezar_atencion(actividad)
    if not error:
        flash('Atención iniciada.', 'success')
    return error


def _terminar(actividad):
    if not current_user.tiene_permiso('agenda_completar'):
        return 'No tienes permiso para terminar turnos.'
    error = terminar_turno(actividad)
    if not error:
        flash('Turno terminado. Queda en Cobros pendientes hasta que lo cobres.', 'success')
    return error


_ACCIONES = {
    'reprogramar': _reprogramar,
    'sena': _registrar_sena,
    'cancelar': lambda actividad: _cerrar(actividad, 'cancelar'),
    'no_show': lambda actividad: _cerrar(actividad, 'no_show'),
    'empezar': _empezar,
    'terminar': _terminar,
}


@agenda_bp.route('/turnos/peluqueria/<int:id_actividad>/gestionar', methods=['GET', 'POST'])
@login_required
def gestionar_turno_peluqueria(id_actividad):
    actividad = _cargar_turno_peluqueria_visible_o_404(id_actividad)
    if request.method == 'GET':
        return _render_gestion(actividad)

    accion = _ACCIONES.get((request.form.get('accion') or '').strip().lower())
    if accion is None:
        flash('Acción no válida para este turno.', 'warning')
        return _redirect_gestion_turno(actividad)
    error = accion(actividad)
    if error:
        db.session.rollback()
        flash(error, 'warning')
        return _redirect_gestion_turno(actividad)
    db.session.commit()
    return _redirect_gestion_turno(actividad)


@agenda_bp.route('/turnos/peluqueria/<int:id_actividad>/cobrar', methods=['GET'])
@login_required
def cobrar_turno_peluqueria(id_actividad):
    actividad = _cargar_turno_peluqueria_visible_o_404(id_actividad)
    url = url_cobro_turno(actividad) if current_user.tiene_permiso('crear_venta') else None
    if not url:
        flash('Este turno ya fue cobrado o no tienes permiso para cobrar.', 'warning')
        return _redirect_gestion_turno(actividad)
    return redirect(url)
