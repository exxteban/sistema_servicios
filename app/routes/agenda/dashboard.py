from datetime import timedelta

from flask import render_template, request, url_for
from flask_login import login_required, current_user
from sqlalchemy import and_, case
from sqlalchemy.orm import joinedload, load_only

from app import db
from app.models import AgendaActividad, Cliente, ClienteServicio, Reparacion, Servicio, Usuario, Venta
from app.routes.agenda import agenda_bp
from app.routes.agenda.visibilidad import (
    filtro_mostrar_agenda_para_usuario,
    obtener_root_user_id_sistema,
    usuarios_agenda_visibles_para,
)
from app.utils.perf import perf_section
from app.utils.helpers import local_strftime, parse_iso_date, today_local, utc_bounds_for_local_dates

PRIORIDADES_ACTIVIDAD = ('baja', 'media', 'alta', 'critica')
TIPOS_ACTIVIDAD = ('cita', 'llamada', 'entrega', 'cobro', 'seguimiento', 'tarea_interna', 'recordatorio')
ESTADOS_ACTIVIDAD = ('pendiente', 'hecha', 'cancelada')

TIPO_LABELS = {
    'cita': 'Cita',
    'llamada': 'Llamada',
    'entrega': 'Entrega',
    'cobro': 'Cobro',
    'seguimiento': 'Seguimiento',
    'tarea_interna': 'Tarea interna',
    'recordatorio': 'Recordatorio',
}


def _puede_ver_todo():
    return current_user.es_admin() or current_user.tiene_permiso('agenda_ver_todas')


def _query_visible():
    query = AgendaActividad.query
    if _puede_ver_todo():
        visible_query = query
    else:
        visible_query = query.filter(filtro_mostrar_agenda_para_usuario(current_user.id_usuario))
    root_id = obtener_root_user_id_sistema()
    if root_id:
        visible_query = visible_query.filter(AgendaActividad.usuario_id != root_id)
    return visible_query


def _resolver_rango_operativo():
    fecha_base = parse_iso_date(request.args.get('fecha')) or today_local()
    vista = (request.args.get('vista') or 'dia').strip().lower()
    if vista not in ('dia', 'semana'):
        vista = 'dia'
    if vista == 'semana':
        desde = fecha_base - timedelta(days=fecha_base.weekday())
        hasta = desde + timedelta(days=6)
    else:
        desde = fecha_base
        hasta = fecha_base
    return vista, fecha_base, desde, hasta


def _resolver_filtros_operativos():
    estado = (request.args.get('estado') or 'todos').strip().lower()
    tipo = (request.args.get('tipo') or '').strip().lower()
    responsable_id = request.args.get('responsable_id', type=int)
    if estado not in ESTADOS_ACTIVIDAD and estado != 'todos':
        estado = 'todos'
    if tipo not in TIPOS_ACTIVIDAD:
        tipo = ''
    if not _puede_ver_todo():
        responsable_id = current_user.id_usuario
    return {
        'estado': estado,
        'tipo': tipo,
        'responsable_id': responsable_id,
    }


def _actividad_options():
    return (
        load_only(
            AgendaActividad.id,
            AgendaActividad.titulo,
            AgendaActividad.tipo,
            AgendaActividad.fecha_inicio,
            AgendaActividad.fecha_fin,
            AgendaActividad.estado,
            AgendaActividad.prioridad,
            AgendaActividad.usuario_id,
            AgendaActividad.cliente_id,
            AgendaActividad.cliente_servicio_id,
            AgendaActividad.reparacion_id,
            AgendaActividad.venta_id,
            AgendaActividad.observaciones,
        ),
        joinedload(AgendaActividad.usuario).load_only(
            Usuario.id_usuario,
            Usuario.nombre_completo,
            Usuario.username,
        ),
        joinedload(AgendaActividad.cliente).load_only(
            Cliente.id_cliente,
            Cliente.nombre,
            Cliente.telefono,
        ),
        joinedload(AgendaActividad.cliente_servicio)
        .joinedload(ClienteServicio.cliente)
        .load_only(Cliente.id_cliente, Cliente.nombre, Cliente.telefono),
        joinedload(AgendaActividad.cliente_servicio)
        .joinedload(ClienteServicio.servicio)
        .load_only(Servicio.id_servicio, Servicio.nombre, Servicio.duracion_minutos),
        joinedload(AgendaActividad.reparacion)
        .joinedload(Reparacion.cliente)
        .load_only(Cliente.id_cliente, Cliente.nombre, Cliente.telefono),
        joinedload(AgendaActividad.venta)
        .joinedload(Venta.cliente)
        .load_only(Cliente.id_cliente, Cliente.nombre, Cliente.telefono),
    )


def _query_actividades_operativas(desde, hasta, filtros):
    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)
    query = (
        _query_visible()
        .options(*_actividad_options())
        .filter(AgendaActividad.fecha_inicio >= start_utc, AgendaActividad.fecha_inicio < end_utc)
    )
    if filtros['estado'] != 'todos':
        query = query.filter(AgendaActividad.estado == filtros['estado'])
    if filtros['tipo']:
        query = query.filter(AgendaActividad.tipo == filtros['tipo'])
    if filtros['responsable_id']:
        query = query.filter(AgendaActividad.usuario_id == filtros['responsable_id'])
    return query.order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.asc()).limit(160).all()


def _cliente_label(actividad):
    candidatos = [
        getattr(actividad, 'cliente', None),
        getattr(getattr(actividad, 'cliente_servicio', None), 'cliente', None),
        getattr(getattr(actividad, 'reparacion', None), 'cliente', None),
        getattr(getattr(actividad, 'venta', None), 'cliente', None),
    ]
    for cliente in candidatos:
        if cliente and getattr(cliente, 'nombre', None):
            return cliente.nombre, getattr(cliente, 'telefono', '') or ''
    return 'Sin cliente', ''


def _servicio_label(actividad):
    asignacion = getattr(actividad, 'cliente_servicio', None)
    servicio = getattr(asignacion, 'servicio', None)
    if servicio and getattr(servicio, 'nombre', None):
        return servicio.nombre, getattr(asignacion, 'estado', '') or ''
    reparacion = getattr(actividad, 'reparacion', None)
    if reparacion:
        equipo = ' '.join(filter(None, [getattr(reparacion, 'tipo_equipo', ''), getattr(reparacion, 'marca_modelo', '')]))
        return equipo or 'Reparacion', getattr(reparacion, 'estado', '') or ''
    return TIPO_LABELS.get(actividad.tipo, 'Actividad'), ''


def _monto_estimado(actividad):
    asignacion = getattr(actividad, 'cliente_servicio', None)
    if not asignacion:
        return 0
    try:
        return float(asignacion.subtotal or 0)
    except Exception:
        return 0


def _serializar_actividad_operativa(actividad):
    cliente, telefono = _cliente_label(actividad)
    servicio, servicio_estado = _servicio_label(actividad)
    responsable = getattr(actividad, 'usuario', None)
    return {
        'actividad': actividad,
        'id': actividad.id,
        'titulo': actividad.titulo,
        'tipo_label': TIPO_LABELS.get(actividad.tipo, (actividad.tipo or 'Actividad').replace('_', ' ').title()),
        'cliente': cliente,
        'telefono': telefono,
        'servicio': servicio,
        'servicio_estado': servicio_estado,
        'responsable_id': actividad.usuario_id,
        'responsable': (responsable.nombre_completo or responsable.username) if responsable else 'Sin responsable',
        'hora_inicio': local_strftime(actividad.fecha_inicio, '%H:%M'),
        'hora_fin': local_strftime(actividad.fecha_fin, '%H:%M') if actividad.fecha_fin else '',
        'fecha_label': local_strftime(actividad.fecha_inicio, '%d/%m/%Y'),
        'fecha_reprogramar': local_strftime(actividad.fecha_inicio, '%Y-%m-%dT%H:%M'),
        'estado': actividad.estado,
        'prioridad': actividad.prioridad,
        'monto': _monto_estimado(actividad),
        'observaciones': actividad.observaciones or '',
    }


def _agrupar_por_responsable(cards, responsables):
    grupos = []
    por_responsable = {}
    for card in cards:
        por_responsable.setdefault(card['responsable_id'], []).append(card)
    ids_con_actividad = set(por_responsable)
    for usuario in responsables:
        user_id = usuario.id_usuario
        grupos.append(
            {
                'id': user_id,
                'nombre': usuario.nombre_completo or usuario.username,
                'items': por_responsable.pop(user_id, []),
            }
        )
    for user_id, items in por_responsable.items():
        grupos.append({'id': user_id, 'nombre': items[0]['responsable'], 'items': items})
    return grupos, ids_con_actividad


def _opciones_responsables():
    return usuarios_agenda_visibles_para(current_user, _puede_ver_todo())


def _navegacion_rango(vista, fecha_base):
    delta = timedelta(days=7 if vista == 'semana' else 1)
    return {
        'prev_url': url_for('agenda.dashboard', **{**request.args.to_dict(), 'fecha': (fecha_base - delta).isoformat()}),
        'next_url': url_for('agenda.dashboard', **{**request.args.to_dict(), 'fecha': (fecha_base + delta).isoformat()}),
        'today_url': url_for('agenda.dashboard', **{**request.args.to_dict(), 'fecha': today_local().isoformat()}),
    }


@agenda_bp.route('/', methods=['GET'])
@agenda_bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    vista, fecha_base, desde, hasta = _resolver_rango_operativo()
    filtros = _resolver_filtros_operativos()
    today = today_local()
    start_utc, end_utc = utc_bounds_for_local_dates(today, today)
    pending_query = _query_visible().filter(AgendaActividad.estado == 'pendiente')

    rango_hoy = and_(AgendaActividad.fecha_inicio >= start_utc, AgendaActividad.fecha_inicio < end_utc)
    with perf_section('agenda-dashboard-counts'):
        pendientes_hoy, vencidas, proximas = (
            pending_query.with_entities(
                db.func.coalesce(db.func.sum(case((rango_hoy, 1), else_=0)), 0),
                db.func.coalesce(db.func.sum(case((AgendaActividad.fecha_inicio < start_utc, 1), else_=0)), 0),
                db.func.coalesce(db.func.sum(case((AgendaActividad.fecha_inicio >= end_utc, 1), else_=0)), 0),
            ).one()
        )
    with perf_section('agenda-dashboard-priorities'):
        prioridades_rows = (
            pending_query.with_entities(
                AgendaActividad.prioridad,
                db.func.count(AgendaActividad.id),
            )
            .group_by(AgendaActividad.prioridad)
            .all()
        )
    prioridades_pendientes = {prioridad: 0 for prioridad in PRIORIDADES_ACTIVIDAD}
    for prioridad, total in prioridades_rows:
        if prioridad in prioridades_pendientes:
            prioridades_pendientes[prioridad] = total
    responsables = _opciones_responsables()
    with perf_section('agenda-dashboard-operativa'):
        actividades = _query_actividades_operativas(desde, hasta, filtros)
    cards = [_serializar_actividad_operativa(actividad) for actividad in actividades]
    grupos_responsables, responsables_ocupados = _agrupar_por_responsable(cards, responsables)
    estados_rango = {estado: 0 for estado in ESTADOS_ACTIVIDAD}
    ingresos_estimados = 0
    for card in cards:
        if card['estado'] in estados_rango:
            estados_rango[card['estado']] += 1
        ingresos_estimados += card['monto']
    total_responsables = len(responsables)
    libres = max(total_responsables - len(responsables_ocupados), 0)
    rango_label = (
        desde.strftime('%d/%m/%Y')
        if desde == hasta
        else f"{desde.strftime('%d/%m/%Y')} - {hasta.strftime('%d/%m/%Y')}"
    )

    return render_template(
        'agenda/dashboard.html',
        pendientes_hoy=pendientes_hoy,
        vencidas=vencidas,
        proximas=proximas,
        prioridades_pendientes=prioridades_pendientes,
        fecha_hoy=today,
        fecha_base=fecha_base,
        vista=vista,
        desde=desde,
        hasta=hasta,
        rango_label=rango_label,
        filtros=filtros,
        responsables=responsables,
        grupos_responsables=grupos_responsables,
        estados_rango=estados_rango,
        ingresos_estimados=ingresos_estimados,
        total_actividades=len(cards),
        responsables_ocupados=len(responsables_ocupados),
        responsables_libres=libres,
        navegacion=_navegacion_rango(vista, fecha_base),
        tipos_actividad=TIPOS_ACTIVIDAD,
        tipo_labels=TIPO_LABELS,
    )
