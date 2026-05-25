from datetime import timedelta

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import AgendaActividad, Cliente, ClienteServicio, Usuario
from app.routes.agenda import agenda_bp
from app.routes.agenda.actividades import _parse_datetime_local
from app.routes.agenda.visibilidad import filtro_mostrar_agenda_para_usuario, usuarios_agenda_visibles_para
from app.services.agenda_turnos_peluqueria import (
    build_turno_peluqueria_chargeable_catalog_services,
    build_turno_peluqueria_services,
    catalog_service_requires_price_option,
    get_turno_peluqueria_catalog_service,
    get_turno_peluqueria_catalog_price_option,
    is_turno_peluqueria_catalog_service_chargeable,
    is_turno_peluqueria_pos_chargeable,
    parse_turno_manual_price,
    resolve_turno_peluqueria_catalog_service,
)
from app.utils.helpers import utc_naive_to_local

HORARIOS_TURNO_PELUQUERIA = tuple(
    f'{hora:02d}:{minuto:02d}'
    for hora in range(8, 21)
    for minuto in (0, 30)
)


def _puede_asignar_profesional():
    return current_user.es_admin() or current_user.tiene_permiso('agenda_ver_todas')


def _serializar_profesional(usuario):
    return {
        'id': usuario.id_usuario,
        'nombre': usuario.nombre_completo or usuario.username,
        'iniciales': _iniciales_usuario(usuario),
    }


def _iniciales_usuario(usuario):
    nombre = usuario.nombre_completo or usuario.username or 'P'
    partes = [parte[0] for parte in nombre.split() if parte]
    return ''.join(partes[:2]).upper() or 'P'


def _obtener_profesionales_disponibles():
    return usuarios_agenda_visibles_para(current_user, _puede_asignar_profesional())


def _parse_positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _build_turno_redirect_pos_params(*, cliente_id=None, servicio_catalogo_id=None, profesional_id=None, manual_price=None, title=None, price_option_id=None):
    params = {}
    cliente_id = _parse_positive_int(cliente_id)
    profesional_id = _parse_positive_int(profesional_id)
    servicio = get_turno_peluqueria_catalog_service(servicio_catalogo_id)
    price_option = get_turno_peluqueria_catalog_price_option(servicio, price_option_id)
    if cliente_id:
        params['agenda_turno_cliente_id'] = cliente_id
    if profesional_id:
        params['agenda_turno_vendedor_id'] = profesional_id
    if is_turno_peluqueria_pos_chargeable(servicio, manual_price, price_option=price_option):
        params['agenda_turno_servicio_id'] = int(servicio.id_servicio)
    if price_option is not None:
        params['agenda_turno_precio_opcion_id'] = int(price_option.id_opcion_precio)
    if manual_price is not None:
        params['agenda_turno_precio_manual'] = str(manual_price)
    if title:
        params['agenda_turno_titulo'] = str(title).strip()
    return params


def _validar_datos_turno_rapido(form):
    servicio_nombre = (form.get('servicio_turno_nombre') or '').strip()
    fecha_inicio = _parse_datetime_local(form.get('fecha_inicio'))
    duracion = _parse_positive_int(form.get('duracion')) or 30
    fecha_fin = _parse_datetime_local(form.get('fecha_fin'))
    if fecha_inicio and (fecha_fin is None or fecha_fin <= fecha_inicio):
        fecha_fin = fecha_inicio + timedelta(minutes=duracion)
    if not servicio_nombre:
        return None, 'Selecciona un servicio para el turno.'
    if fecha_inicio is None:
        return None, 'Completa una fecha y hora validas para el turno.'
    return {
        'servicio_nombre': servicio_nombre,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
    }, None


def _crear_cliente_servicio_turno(*, cliente_id, servicio_catalogo_id, fecha_inicio, observaciones, precio_manual=None, price_option_id=None):
    servicio = resolve_turno_peluqueria_catalog_service(servicio_id=servicio_catalogo_id)
    price_option = get_turno_peluqueria_catalog_price_option(servicio, price_option_id)
    if servicio is None or not cliente_id or not is_turno_peluqueria_pos_chargeable(servicio, precio_manual, price_option=price_option):
        return None
    costo_pactado = price_option.costo if price_option is not None else (servicio.costo or 0)
    precio_pactado = precio_manual if precio_manual is not None else (price_option.precio if price_option is not None else (servicio.precio or 0))
    asignacion = ClienteServicio(
        id_cliente=cliente_id,
        id_servicio=servicio.id_servicio,
        cantidad=1,
        costo_pactado=costo_pactado,
        precio_pactado=precio_pactado,
        estado='agendado',
        fecha_programada=fecha_inicio,
        observaciones=observaciones,
        id_usuario_registro=current_user.id_usuario,
    )
    db.session.add(asignacion)
    db.session.flush()
    return asignacion


def _buscar_turno_solapado(*, profesional_id, fecha_inicio, fecha_fin, excluir_actividad_id=None):
    if not profesional_id or not fecha_inicio or not fecha_fin:
        return None
    query = (
        AgendaActividad.query
        .filter(
            AgendaActividad.usuario_id == profesional_id,
            AgendaActividad.tipo == 'cita',
            AgendaActividad.estado == 'pendiente',
            AgendaActividad.fecha_inicio < fecha_fin,
            db.or_(AgendaActividad.fecha_fin.is_(None), AgendaActividad.fecha_fin > fecha_inicio),
        )
    )
    actividad_id = _parse_positive_int(excluir_actividad_id)
    if actividad_id:
        query = query.filter(AgendaActividad.id != actividad_id)
    return query.order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.asc()).first()


def _crear_cliente_rapido_turno(form):
    nombre = (form.get('cliente_nuevo_nombre') or '').strip()
    if not nombre:
        return None, None
    if not current_user.tiene_permiso('crear_cliente'):
        return None, 'No tienes permiso para crear clientes desde el turno.'

    cliente = Cliente(
        nombre=nombre,
        telefono=(form.get('cliente_nuevo_telefono') or '').strip() or None,
        tipo='minorista',
        activo=True,
    )
    db.session.add(cliente)
    db.session.flush()
    return cliente, None


def _query_turnos_peluqueria_visibles():
    query = AgendaActividad.query.filter(AgendaActividad.tipo == 'cita')
    if not _puede_asignar_profesional():
        query = query.filter(filtro_mostrar_agenda_para_usuario(current_user.id_usuario))
    return query


def _cargar_turno_peluqueria_visible_o_404(id_actividad):
    return _query_turnos_peluqueria_visibles().filter(AgendaActividad.id == id_actividad).first_or_404()


def _to_date_input(value):
    local_value = utc_naive_to_local(value)
    return local_value.strftime('%Y-%m-%d') if local_value else ''


def _to_time_input(value):
    local_value = utc_naive_to_local(value)
    return local_value.strftime('%H:%M') if local_value else ''


def _duracion_minutos_actividad(actividad):
    if actividad.fecha_inicio and actividad.fecha_fin and actividad.fecha_fin > actividad.fecha_inicio:
        return max(int((actividad.fecha_fin - actividad.fecha_inicio).total_seconds() // 60), 1)
    return 30


def _append_turno_note(actividad, nota):
    nota = (nota or '').strip()
    if not nota:
        return
    actividad.observaciones = '\n'.join(filter(None, [(actividad.observaciones or '').strip(), nota]))
    asignacion = getattr(actividad, 'cliente_servicio', None)
    if asignacion is not None:
        asignacion.observaciones = '\n'.join(filter(None, [(asignacion.observaciones or '').strip(), nota]))


def _redirect_gestion_turno(actividad):
    return redirect(url_for('agenda.gestionar_turno_peluqueria', id_actividad=int(actividad.id)))


@agenda_bp.route('/turnos/peluqueria/nuevo', methods=['GET'])
@login_required
def nuevo_turno_peluqueria():
    if not current_user.tiene_permiso('agenda_crear'):
        flash('No tienes permiso para crear turnos.', 'danger')
        return redirect(url_for('agenda.lista_actividades'))

    profesionales = [_serializar_profesional(usuario) for usuario in _obtener_profesionales_disponibles()]
    return render_template(
        'agenda/peluqueria_turno_rapido.html',
        profesionales=profesionales,
        servicios=build_turno_peluqueria_services(),
        servicios_cobrables_catalogo=build_turno_peluqueria_chargeable_catalog_services(),
        horarios=HORARIOS_TURNO_PELUQUERIA,
        puede_ver_agenda=current_user.tiene_permiso('agenda_acceso'),
        puede_crear_venta=current_user.tiene_permiso('crear_venta'),
        puede_crear_cliente=current_user.tiene_permiso('crear_cliente'),
    )


@agenda_bp.route('/turnos/peluqueria/<int:id_actividad>/gestionar', methods=['GET', 'POST'])
@login_required
def gestionar_turno_peluqueria(id_actividad):
    actividad = _cargar_turno_peluqueria_visible_o_404(id_actividad)
    if request.method == 'GET':
        return render_template(
            'agenda/peluqueria_gestionar_turno.html',
            actividad=actividad,
            fecha_actual=_to_date_input(actividad.fecha_inicio),
            hora_actual=_to_time_input(actividad.fecha_inicio),
            duracion_actual=_duracion_minutos_actividad(actividad),
            puede_reprogramar=current_user.tiene_permiso('agenda_editar'),
            puede_cancelar=current_user.tiene_permiso('agenda_cancelar'),
            puede_registrar_sena=(current_user.tiene_permiso('agenda_editar') or current_user.tiene_permiso('crear_venta')),
        )

    accion = (request.form.get('accion') or '').strip().lower()
    if accion == 'reprogramar':
        if not current_user.tiene_permiso('agenda_editar'):
            flash('No tienes permiso para reprogramar turnos.', 'danger')
            return _redirect_gestion_turno(actividad)
        fecha_inicio = _parse_datetime_local(f"{request.form.get('fecha') or ''}T{request.form.get('hora') or ''}")
        duracion = _parse_positive_int(request.form.get('duracion')) or _duracion_minutos_actividad(actividad)
        if fecha_inicio is None:
            flash('Completa una fecha y hora validas para reprogramar.', 'warning')
            return _redirect_gestion_turno(actividad)
        fecha_fin = fecha_inicio + timedelta(minutes=duracion)
        turno_solapado = _buscar_turno_solapado(
            profesional_id=actividad.usuario_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            excluir_actividad_id=actividad.id,
        )
        if turno_solapado is not None:
            flash('Ese profesional ya tiene otro turno en ese horario.', 'warning')
            return _redirect_gestion_turno(actividad)
        actividad.fecha_inicio = fecha_inicio
        actividad.fecha_fin = fecha_fin
        actividad.estado = 'pendiente'
        if actividad.cliente_servicio is not None:
            actividad.cliente_servicio.fecha_programada = fecha_inicio
            if (actividad.cliente_servicio.estado or '').strip().lower() in {'solicitado', 'presupuestado', 'cancelado'}:
                actividad.cliente_servicio.estado = 'agendado'
                actividad.cliente_servicio.fecha_cierre = None
        flash('Turno reprogramado correctamente.', 'success')
    elif accion == 'sena':
        if not (current_user.tiene_permiso('agenda_editar') or current_user.tiene_permiso('crear_venta')):
            flash('No tienes permiso para registrar señas.', 'danger')
            return _redirect_gestion_turno(actividad)
        monto = parse_turno_manual_price(request.form.get('monto_sena'))
        if monto is None:
            flash('Ingresa un monto de seña mayor a cero.', 'warning')
            return _redirect_gestion_turno(actividad)
        nota = (request.form.get('nota_sena') or '').strip()
        _append_turno_note(actividad, f'Seña registrada: Gs. {int(monto):,}'.replace(',', '.') + (f' - {nota}' if nota else ''))
        flash('Seña registrada como nota del turno.', 'success')
    elif accion in {'cancelar', 'no_show'}:
        if not current_user.tiene_permiso('agenda_cancelar'):
            flash('No tienes permiso para cerrar turnos.', 'danger')
            return _redirect_gestion_turno(actividad)
        motivo = (request.form.get('motivo') or '').strip()
        etiqueta = 'No-show' if accion == 'no_show' else 'Cancelado'
        actividad.estado = 'cancelada'
        if actividad.cliente_servicio is not None and not actividad.cliente_servicio.id_venta:
            actividad.cliente_servicio.estado = 'cancelado'
        _append_turno_note(actividad, f'{etiqueta} desde peluquería/barbería' + (f': {motivo}' if motivo else '.'))
        flash('Turno marcado como no-show.' if accion == 'no_show' else 'Turno cancelado correctamente.', 'success')
    else:
        flash('Acción no válida para este turno.', 'warning')
        return _redirect_gestion_turno(actividad)

    db.session.commit()
    return _redirect_gestion_turno(actividad)


@agenda_bp.route('/turnos/peluqueria/crear', methods=['POST'])
@login_required
def crear_turno_peluqueria():
    if not current_user.tiene_permiso('agenda_crear'):
        flash('No tienes permiso para crear turnos.', 'danger')
        return redirect(url_for('agenda.lista_actividades'))

    turno_data, error = _validar_datos_turno_rapido(request.form)
    if error:
        flash(error, 'warning')
        return redirect(url_for('agenda.nuevo_turno_peluqueria'))

    profesional_id = request.form.get('usuario_id', type=int) or current_user.id_usuario
    if not _puede_asignar_profesional():
        profesional_id = current_user.id_usuario

    profesional = db.session.get(Usuario, profesional_id)
    if profesional is None or not getattr(profesional, 'activo', True):
        flash('Selecciona un profesional activo para el turno.', 'warning')
        return redirect(url_for('agenda.nuevo_turno_peluqueria'))

    turno_solapado = _buscar_turno_solapado(
        profesional_id=profesional_id,
        fecha_inicio=turno_data['fecha_inicio'],
        fecha_fin=turno_data['fecha_fin'],
    )
    if turno_solapado is not None:
        flash('Ese profesional ya tiene un turno en ese horario. Elige otra hora o profesional.', 'warning')
        return redirect(url_for('agenda.nuevo_turno_peluqueria'))

    observaciones = (request.form.get('observaciones') or '').strip() or None
    precio_manual = parse_turno_manual_price(request.form.get('precio_manual'))
    servicio_precio_opcion_id = request.form.get('servicio_precio_opcion_id')
    servicio_resuelto = resolve_turno_peluqueria_catalog_service(
        servicio_id=request.form.get('servicio_catalogo_id'),
        turno_tipo_id=request.form.get('servicio_turno_id'),
        title=request.form.get('servicio_turno_nombre'),
    )
    servicio_precio_opcion = get_turno_peluqueria_catalog_price_option(servicio_resuelto, servicio_precio_opcion_id)
    if catalog_service_requires_price_option(servicio_resuelto) and servicio_precio_opcion is None:
        flash('Selecciona el tipo o variante del servicio antes de crear el turno.', 'warning')
        return redirect(url_for('agenda.nuevo_turno_peluqueria'))

    cliente_id = _parse_positive_int(request.form.get('cliente_id'))
    if not cliente_id:
        cliente_nuevo, error_cliente = _crear_cliente_rapido_turno(request.form)
        if error_cliente:
            flash(error_cliente, 'warning')
            return redirect(url_for('agenda.nuevo_turno_peluqueria'))
        if cliente_nuevo is not None:
            cliente_id = int(cliente_nuevo.id_cliente)

    asignacion = _crear_cliente_servicio_turno(
        cliente_id=cliente_id,
        servicio_catalogo_id=(int(servicio_resuelto.id_servicio) if servicio_resuelto else None),
        fecha_inicio=turno_data['fecha_inicio'],
        observaciones=observaciones,
        precio_manual=precio_manual,
        price_option_id=servicio_precio_opcion_id,
    )
    actividad = AgendaActividad(
        titulo=(request.form.get('titulo') or '').strip() or turno_data['servicio_nombre'],
        tipo='cita',
        descripcion=(request.form.get('descripcion') or '').strip() or None,
        fecha_inicio=turno_data['fecha_inicio'],
        fecha_fin=turno_data['fecha_fin'],
        estado='pendiente',
        prioridad='media',
        usuario_id=profesional_id,
        creado_por_id=current_user.id_usuario,
        cliente_id=cliente_id,
        cliente_servicio_id=(int(asignacion.id_cliente_servicio) if asignacion else None),
        origen_modulo='agenda',
        mostrar_agenda_en='solo_responsable',
        recordatorio_a='solo_responsable',
        recordatorio_minutos=15,
        observaciones=observaciones,
    )
    db.session.add(actividad)
    db.session.commit()

    flash('Turno creado correctamente.', 'success')
    accion = (request.form.get('accion') or 'crear').strip().lower()
    servicio_cobrable = is_turno_peluqueria_pos_chargeable(servicio_resuelto, precio_manual, price_option=servicio_precio_opcion)
    if not servicio_cobrable:
        flash(
            'El turno se creó sin un servicio cobrable vinculado. Configura la opcion en Servicios para que aparezca en Cobros pendientes y se pueda cobrar directo.',
            'warning',
        )
    if accion == 'crear_y_cobrar' and current_user.tiene_permiso('crear_venta'):
        if asignacion is not None:
            return redirect(url_for('ventas.pos', cliente_servicio_id=int(asignacion.id_cliente_servicio)))
        if not servicio_cobrable:
            flash('No se puede abrir POS para este turno porque no tiene un servicio del catalogo con precio valido.', 'warning')
            return redirect(url_for('agenda.lista_actividades'))
        redirect_params = _build_turno_redirect_pos_params(
            cliente_id=cliente_id,
            servicio_catalogo_id=request.form.get('servicio_catalogo_id'),
            profesional_id=profesional_id,
            manual_price=precio_manual,
            title=(request.form.get('titulo') or '').strip() or turno_data['servicio_nombre'],
            price_option_id=servicio_precio_opcion_id,
        )
        return redirect(url_for('ventas.pos', **redirect_params))

    return redirect(url_for('agenda.lista_actividades'))
