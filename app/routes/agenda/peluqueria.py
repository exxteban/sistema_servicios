from datetime import timedelta

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import AgendaActividad, ClienteServicio, Usuario
from app.routes.agenda import agenda_bp
from app.routes.agenda.actividades import _parse_datetime_local
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
    if not _puede_asignar_profesional():
        return [current_user]
    return Usuario.query.filter_by(activo=True).order_by(Usuario.nombre_completo.asc()).all()


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
    )


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

    cliente_id = _parse_positive_int(request.form.get('cliente_id'))
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
