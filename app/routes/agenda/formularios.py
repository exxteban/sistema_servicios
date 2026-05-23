from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import AgendaActividad
from app.routes.agenda import agenda_bp
from app.routes.agenda.actividades import (
    ALCANCES_DESTINATARIOS,
    PRIORIDADES_ACTIVIDAD,
    PRIORIDADES_ACTIVIDAD_LABELS,
    TIPOS_ACTIVIDAD,
    TIPOS_ACTIVIDAD_LABELS,
    _aplicar_destinatarios_a_actividad,
    _limpiar_destinatarios_actividad,
    _parse_datetime_local,
    _parse_optional_int,
    _puede_ver_todo,
    _query_visible,
    _resolver_destinatarios_formulario,
    _resolver_estado_alerta,
    _to_datetime_local_input,
    _validar_destinatarios,
    _validar_temporalidad_actividad,
    _wants_json_response,
)
from app.routes.agenda.relaciones import (
    _obtener_opciones_formulario,
    _obtener_relaciones_iniciales,
    _resolver_cliente_servicio_agenda,
)


def _render_formulario_actividad(
    modo,
    actividad,
    data,
    usuarios,
    contactos,
    cliente_inicial,
    cliente_servicio_inicial,
    servicio_inicial,
    reparacion_inicial,
    venta_inicial,
):
    mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids = _resolver_destinatarios_formulario(
        data=data,
        actividad=actividad,
    )
    return render_template(
        'agenda/form.html',
        modo=modo,
        actividad=actividad,
        data=data,
        tipos_actividad=TIPOS_ACTIVIDAD,
        estados_actividad=('pendiente', 'hecha', 'cancelada'),
        prioridades_actividad=PRIORIDADES_ACTIVIDAD,
        alcances_destinatarios=ALCANCES_DESTINATARIOS,
        tipos_labels=TIPOS_ACTIVIDAD_LABELS,
        prioridades_labels=PRIORIDADES_ACTIVIDAD_LABELS,
        usuarios=usuarios,
        contactos=contactos,
        mostrar_agenda_en=mostrar_agenda_en,
        usuarios_agenda_ids=usuarios_agenda_ids,
        recordatorio_a=recordatorio_a,
        usuarios_recordatorio_ids=usuarios_recordatorio_ids,
        cliente_inicial=cliente_inicial,
        cliente_servicio_inicial=cliente_servicio_inicial,
        servicio_inicial=servicio_inicial,
        reparacion_inicial=reparacion_inicial,
        venta_inicial=venta_inicial,
        to_datetime_local_input=_to_datetime_local_input,
    )


def _cargar_actividad_visible_o_404(id_actividad: int):
    return _query_visible().filter(AgendaActividad.id == id_actividad).first_or_404()


def _redirect_agenda_next(default_endpoint='agenda.lista_actividades'):
    next_url = (request.form.get('next') or request.args.get('next') or '').strip()
    if next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return url_for(default_endpoint)


def _sincronizar_cliente_servicio_desde_actividad(actividad: AgendaActividad, *, accion: str):
    asignacion = getattr(actividad, 'cliente_servicio', None)
    if asignacion is None:
        return
    estado = (asignacion.estado or '').strip().lower()
    if accion == 'iniciar' and estado in {'solicitado', 'agendado', 'presupuestado'}:
        asignacion.estado = 'en_proceso'
        return
    if accion == 'completar' and estado != 'cancelado':
        asignacion.estado = 'completado'
        if not asignacion.fecha_cierre:
            asignacion.fecha_cierre = datetime.utcnow()
        return
    if accion == 'cancelar' and not getattr(asignacion, 'id_venta', None):
        asignacion.estado = 'cancelado'
        if not asignacion.fecha_cierre:
            asignacion.fecha_cierre = datetime.utcnow()
        return
    if accion == 'reprogramar':
        asignacion.fecha_programada = actividad.fecha_inicio
        if estado in {'solicitado', 'presupuestado', 'cancelado'}:
            asignacion.estado = 'agendado'
            asignacion.fecha_cierre = None


@agenda_bp.route('/actividades/nueva', methods=['GET', 'POST'])
@login_required
def nueva_actividad():
    if not current_user.tiene_permiso('agenda_crear'):
        flash('No tienes permiso para crear actividades.', 'danger')
        return redirect(url_for('agenda.lista_actividades'))

    usuarios, contactos = _obtener_opciones_formulario()
    cliente_inicial, cliente_servicio_inicial, servicio_inicial, reparacion_inicial, venta_inicial = _obtener_relaciones_iniciales()
    if request.method == 'POST':
        titulo = (request.form.get('titulo') or '').strip()
        tipo = (request.form.get('tipo') or '').strip().lower() or 'cita'
        prioridad = (request.form.get('prioridad') or '').strip().lower() or 'media'
        fecha_inicio = _parse_datetime_local(request.form.get('fecha_inicio'))
        fecha_fin = _parse_datetime_local(request.form.get('fecha_fin'))
        recordatorio_minutos = _parse_optional_int(request.form.get('recordatorio_minutos'))
        cliente_inicial, cliente_servicio_inicial, servicio_inicial, reparacion_inicial, venta_inicial = _obtener_relaciones_iniciales(data=request.form)
        mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids = _resolver_destinatarios_formulario(data=request.form)
        error_destinatarios = _validar_destinatarios(mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids)
        error_temporalidad = _validar_temporalidad_actividad(fecha_inicio, fecha_fin, recordatorio_minutos)

        if not titulo or not fecha_inicio or error_destinatarios or error_temporalidad:
            flash(error_destinatarios or error_temporalidad or 'Titulo y fecha de inicio son obligatorios.', 'warning')
            return _render_formulario_actividad('crear', None, request.form, usuarios, contactos, cliente_inicial, cliente_servicio_inicial, servicio_inicial, reparacion_inicial, venta_inicial)

        usuario_id = request.form.get('usuario_id', type=int) or current_user.id_usuario
        if not _puede_ver_todo():
            usuario_id = current_user.id_usuario
        asignacion_servicio = _resolver_cliente_servicio_agenda(request.form, fecha_inicio)
        actividad = AgendaActividad(
            titulo=titulo,
            tipo=tipo if tipo in TIPOS_ACTIVIDAD else 'cita',
            descripcion=(request.form.get('descripcion') or '').strip() or None,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            estado='pendiente',
            prioridad=prioridad if prioridad in PRIORIDADES_ACTIVIDAD else 'media',
            usuario_id=usuario_id,
            creado_por_id=current_user.id_usuario,
            cliente_id=asignacion_servicio.id_cliente if asignacion_servicio else _parse_optional_int(request.form.get('cliente_id')),
            cliente_servicio_id=asignacion_servicio.id_cliente_servicio if asignacion_servicio else None,
            reparacion_id=_parse_optional_int(request.form.get('reparacion_id')),
            venta_id=_parse_optional_int(request.form.get('venta_id')),
            crm_contacto_id=_parse_optional_int(request.form.get('crm_contacto_id')),
            origen_modulo='agenda',
            recordatorio_minutos=recordatorio_minutos,
            es_todo_el_dia=bool(request.form.get('es_todo_el_dia')),
            observaciones=(request.form.get('observaciones') or '').strip() or None,
        )
        _aplicar_destinatarios_a_actividad(actividad, mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids)
        db.session.add(actividad)
        db.session.commit()
        flash('Actividad creada correctamente.', 'success')
        return redirect(url_for('agenda.lista_actividades'))

    return _render_formulario_actividad('crear', None, {}, usuarios, contactos, cliente_inicial, cliente_servicio_inicial, servicio_inicial, reparacion_inicial, venta_inicial)


@agenda_bp.route('/actividades/<int:id_actividad>/editar', methods=['GET', 'POST'])
@login_required
def editar_actividad(id_actividad: int):
    if not current_user.tiene_permiso('agenda_editar'):
        flash('No tienes permiso para editar actividades.', 'danger')
        return redirect(url_for('agenda.lista_actividades'))

    actividad = _cargar_actividad_visible_o_404(id_actividad)
    usuarios, contactos = _obtener_opciones_formulario()
    cliente_inicial, cliente_servicio_inicial, servicio_inicial, reparacion_inicial, venta_inicial = _obtener_relaciones_iniciales(actividad=actividad)

    if request.method == 'POST':
        titulo = (request.form.get('titulo') or '').strip()
        fecha_inicio = _parse_datetime_local(request.form.get('fecha_inicio'))
        fecha_fin = _parse_datetime_local(request.form.get('fecha_fin'))
        recordatorio_minutos = _parse_optional_int(request.form.get('recordatorio_minutos'))
        cliente_inicial, cliente_servicio_inicial, servicio_inicial, reparacion_inicial, venta_inicial = _obtener_relaciones_iniciales(data=request.form, actividad=actividad)
        mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids = _resolver_destinatarios_formulario(data=request.form)
        error_destinatarios = _validar_destinatarios(mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids)
        error_temporalidad = _validar_temporalidad_actividad(fecha_inicio, fecha_fin, recordatorio_minutos)
        if not titulo or not fecha_inicio or error_destinatarios or error_temporalidad:
            flash(error_destinatarios or error_temporalidad or 'Titulo y fecha de inicio son obligatorios.', 'warning')
            return _render_formulario_actividad('editar', actividad, request.form, usuarios, contactos, cliente_inicial, cliente_servicio_inicial, servicio_inicial, reparacion_inicial, venta_inicial)

        actividad.titulo = titulo
        actividad.tipo = (request.form.get('tipo') or '').strip().lower() or actividad.tipo
        if actividad.tipo not in TIPOS_ACTIVIDAD:
            actividad.tipo = 'tarea_interna'
        actividad.descripcion = (request.form.get('descripcion') or '').strip() or None
        actividad.fecha_inicio = fecha_inicio
        actividad.fecha_fin = fecha_fin
        actividad.prioridad = (request.form.get('prioridad') or '').strip().lower() or actividad.prioridad
        if actividad.prioridad not in PRIORIDADES_ACTIVIDAD:
            actividad.prioridad = 'media'
        if _puede_ver_todo():
            actividad.usuario_id = request.form.get('usuario_id', type=int) or actividad.usuario_id
        asignacion_servicio = _resolver_cliente_servicio_agenda(request.form, fecha_inicio)
        actividad.cliente_id = asignacion_servicio.id_cliente if asignacion_servicio else _parse_optional_int(request.form.get('cliente_id'))
        actividad.cliente_servicio_id = asignacion_servicio.id_cliente_servicio if asignacion_servicio else None
        actividad.reparacion_id = _parse_optional_int(request.form.get('reparacion_id'))
        actividad.venta_id = _parse_optional_int(request.form.get('venta_id'))
        actividad.crm_contacto_id = _parse_optional_int(request.form.get('crm_contacto_id'))
        actividad.recordatorio_minutos = recordatorio_minutos
        actividad.es_todo_el_dia = bool(request.form.get('es_todo_el_dia'))
        actividad.observaciones = (request.form.get('observaciones') or '').strip() or None
        _aplicar_destinatarios_a_actividad(actividad, mostrar_agenda_en, usuarios_agenda_ids, recordatorio_a, usuarios_recordatorio_ids)
        db.session.commit()
        flash('Actividad actualizada correctamente.', 'success')
        return redirect(url_for('agenda.lista_actividades'))

    return _render_formulario_actividad('editar', actividad, {}, usuarios, contactos, cliente_inicial, cliente_servicio_inicial, servicio_inicial, reparacion_inicial, venta_inicial)


@agenda_bp.post('/actividades/<int:id_actividad>/iniciar')
@login_required
def iniciar_actividad(id_actividad: int):
    if not (current_user.tiene_permiso('agenda_editar') or current_user.tiene_permiso('agenda_completar')):
        mensaje = 'No tienes permiso para iniciar actividades.'
        if _wants_json_response():
            return jsonify({'ok': False, 'mensaje': mensaje}), 403
        flash(mensaje, 'danger')
        return redirect(_redirect_agenda_next())
    actividad = _cargar_actividad_visible_o_404(id_actividad)
    _sincronizar_cliente_servicio_desde_actividad(actividad, accion='iniciar')
    db.session.commit()
    mensaje = 'Actividad iniciada.'
    if _wants_json_response():
        return jsonify({'ok': True, 'mensaje': mensaje, 'id': actividad.id, 'estado': actividad.estado})
    flash(mensaje, 'success')
    return redirect(_redirect_agenda_next())


@agenda_bp.post('/actividades/<int:id_actividad>/completar')
@login_required
def completar_actividad(id_actividad: int):
    if not current_user.tiene_permiso('agenda_completar'):
        mensaje = 'No tienes permiso para completar actividades.'
        if _wants_json_response():
            return jsonify({'ok': False, 'mensaje': mensaje}), 403
        flash(mensaje, 'danger')
        return redirect(_redirect_agenda_next())
    actividad = _cargar_actividad_visible_o_404(id_actividad)
    estado_alerta = _resolver_estado_alerta(actividad)
    actividad.estado = 'hecha'
    _sincronizar_cliente_servicio_desde_actividad(actividad, accion='completar')
    db.session.commit()
    mensaje = 'Actividad marcada como hecha.'
    if _wants_json_response():
        return jsonify({'ok': True, 'mensaje': mensaje, 'id': actividad.id, 'estado_alerta': estado_alerta, 'estado': actividad.estado})
    flash(mensaje, 'success')
    return redirect(_redirect_agenda_next())


@agenda_bp.post('/actividades/<int:id_actividad>/cancelar')
@login_required
def cancelar_actividad(id_actividad: int):
    if not current_user.tiene_permiso('agenda_cancelar'):
        mensaje = 'No tienes permiso para cancelar actividades.'
        if _wants_json_response():
            return jsonify({'ok': False, 'mensaje': mensaje}), 403
        flash(mensaje, 'danger')
        return redirect(_redirect_agenda_next())
    actividad = _cargar_actividad_visible_o_404(id_actividad)
    estado_alerta = _resolver_estado_alerta(actividad)
    actividad.estado = 'cancelada'
    _sincronizar_cliente_servicio_desde_actividad(actividad, accion='cancelar')
    db.session.commit()
    mensaje = 'Actividad cancelada.'
    if _wants_json_response():
        return jsonify({'ok': True, 'mensaje': mensaje, 'id': actividad.id, 'estado_alerta': estado_alerta, 'estado': actividad.estado})
    flash(mensaje, 'success')
    return redirect(_redirect_agenda_next())


@agenda_bp.post('/actividades/<int:id_actividad>/eliminar')
@login_required
def eliminar_actividad(id_actividad: int):
    if not current_user.tiene_permiso('agenda_cancelar'):
        mensaje = 'No tienes permiso para eliminar actividades.'
        if _wants_json_response():
            return jsonify({'ok': False, 'mensaje': mensaje}), 403
        flash(mensaje, 'danger')
        return redirect(url_for('agenda.lista_actividades'))
    actividad = _cargar_actividad_visible_o_404(id_actividad)
    estado_alerta = _resolver_estado_alerta(actividad)
    actividad_id = actividad.id
    _limpiar_destinatarios_actividad(actividad)
    db.session.flush()
    db.session.delete(actividad)
    db.session.commit()
    mensaje = 'Actividad eliminada.'
    if _wants_json_response():
        return jsonify({'ok': True, 'mensaje': mensaje, 'id': actividad_id, 'estado_alerta': estado_alerta, 'estado': 'eliminada', 'eliminada': True})
    flash(mensaje, 'success')
    return redirect(url_for('agenda.lista_actividades'))


@agenda_bp.post('/actividades/<int:id_actividad>/reprogramar')
@login_required
def reprogramar_actividad(id_actividad: int):
    if not current_user.tiene_permiso('agenda_editar'):
        flash('No tienes permiso para reprogramar actividades.', 'danger')
        return redirect(url_for('agenda.lista_actividades'))
    actividad = _cargar_actividad_visible_o_404(id_actividad)
    fecha_inicio = _parse_datetime_local(request.form.get('fecha_inicio'))
    if not fecha_inicio:
        flash('La nueva fecha de inicio es obligatoria.', 'warning')
        return redirect(url_for('agenda.lista_actividades'))
    actividad.fecha_inicio = fecha_inicio
    actividad.estado = 'pendiente'
    _sincronizar_cliente_servicio_desde_actividad(actividad, accion='reprogramar')
    db.session.commit()
    flash('Actividad reprogramada.', 'success')
    return redirect(_redirect_agenda_next())
