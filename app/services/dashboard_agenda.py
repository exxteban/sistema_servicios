from flask_login import current_user
from sqlalchemy import and_, case, or_
from sqlalchemy.orm import joinedload, load_only, noload

from app import db
from app.models import AgendaActividad, Cliente, ClienteServicio, Servicio, Usuario
from app.routes.agenda.visibilidad import (
    filtro_mostrar_agenda_para_usuario,
    obtener_root_user_id_sistema,
)
from app.utils.helpers import local_strftime, utc_bounds_for_local_dates


def _query_agenda_visible(query, usuario=None):
    usuario = usuario or current_user
    root_id = obtener_root_user_id_sistema()
    if root_id:
        query = query.filter(AgendaActividad.usuario_id != root_id)
    if not (usuario.es_admin() or usuario.tiene_permiso('agenda_ver_todas')):
        query = query.filter(filtro_mostrar_agenda_para_usuario(usuario.id_usuario))
    return query


def obtener_resumen_agenda_dashboard(can_ver_agenda, today, usuario=None):
    agenda_fecha_hoy_iso = today.isoformat()
    if not can_ver_agenda:
        return {
            'can_ver_agenda': False,
            'total_pendientes': 0,
            'pendientes_hoy': 0,
            'vencidas': 0,
            'proximas_actividades': [],
            'turnero_actividades': [],
            'fecha_hoy_iso': agenda_fecha_hoy_iso,
        }

    start_utc, end_utc = utc_bounds_for_local_dates(today, today)
    agenda_pendiente_query = _query_agenda_visible(
        AgendaActividad.query.filter(AgendaActividad.estado == 'pendiente'),
        usuario=usuario,
    )

    rango_hoy = and_(AgendaActividad.fecha_inicio >= start_utc, AgendaActividad.fecha_inicio < end_utc)
    total_pendientes, pendientes_hoy, vencidas = (
        agenda_pendiente_query.with_entities(
            db.func.count(AgendaActividad.id),
            db.func.coalesce(db.func.sum(case((rango_hoy, 1), else_=0)), 0),
            db.func.coalesce(db.func.sum(case((AgendaActividad.fecha_inicio < start_utc, 1), else_=0)), 0),
        ).one()
    )
    proximas = (
        agenda_pendiente_query
        .options(
            load_only(
                AgendaActividad.id,
                AgendaActividad.titulo,
                AgendaActividad.tipo,
                AgendaActividad.prioridad,
                AgendaActividad.fecha_inicio,
                AgendaActividad.cliente_servicio_id,
            ),
            joinedload(AgendaActividad.cliente_servicio).load_only(
                ClienteServicio.id_cliente_servicio,
                ClienteServicio.id_venta,
                ClienteServicio.estado,
            ),
            noload(AgendaActividad.usuarios_agenda),
            noload(AgendaActividad.usuarios_recordatorio),
        )
        .filter(rango_hoy)
        .order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.desc())
        .limit(5)
        .all()
    )
    turnero_items = (
        _query_agenda_visible(
            AgendaActividad.query.options(
                load_only(
                    AgendaActividad.id,
                    AgendaActividad.titulo,
                    AgendaActividad.estado,
                    AgendaActividad.fecha_inicio,
                    AgendaActividad.fecha_fin,
                    AgendaActividad.cliente_id,
                    AgendaActividad.cliente_servicio_id,
                    AgendaActividad.usuario_id,
                    AgendaActividad.observaciones,
                    AgendaActividad.venta_id,
                    AgendaActividad.atencion_inicio,
                    AgendaActividad.cierre_motivo,
                    AgendaActividad.servicio_id,
                ),
                joinedload(AgendaActividad.servicio).load_only(Servicio.id_servicio, Servicio.nombre),
                joinedload(AgendaActividad.usuario).load_only(Usuario.id_usuario, Usuario.nombre_completo, Usuario.username),
                joinedload(AgendaActividad.cliente).load_only(Cliente.id_cliente, Cliente.nombre),
                joinedload(AgendaActividad.cliente_servicio).load_only(
                    ClienteServicio.id_cliente_servicio,
                    ClienteServicio.id_venta,
                    ClienteServicio.estado,
                    ClienteServicio.id_servicio,
                ).joinedload(ClienteServicio.servicio).load_only(Servicio.id_servicio, Servicio.nombre),
                noload(AgendaActividad.usuarios_agenda),
                noload(AgendaActividad.usuarios_recordatorio),
            ).filter(
                AgendaActividad.tipo == 'cita',
                rango_hoy,
            ),
            usuario=usuario,
        )
        .order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.asc())
        .limit(80)
        .all()
    )

    return {
        'can_ver_agenda': True,
        'total_pendientes': total_pendientes,
        'pendientes_hoy': pendientes_hoy,
        'vencidas': vencidas,
        'proximas_actividades': [
            {
                'id': actividad.id,
                'titulo': actividad.titulo or '',
                'tipo': actividad.tipo or '',
                'tipo_label': (actividad.tipo or '').replace('_', ' ').title(),
                'prioridad': actividad.prioridad or 'baja',
                'prioridad_label': (actividad.prioridad or 'baja').title(),
                'hora_label': local_strftime(actividad.fecha_inicio, '%H:%M'),
                'cliente_servicio_id': int(actividad.cliente_servicio_id) if actividad.cliente_servicio_id else None,
                'cliente_servicio_estado': ((actividad.cliente_servicio.estado or '').strip().lower() if actividad.cliente_servicio else ''),
                'cliente_servicio_cobrado': bool(actividad.cliente_servicio and actividad.cliente_servicio.id_venta),
            }
            for actividad in proximas
        ],
        'turnero_actividades': [serializar_turno_peluqueria(actividad) for actividad in turnero_items],
        'fecha_hoy_iso': agenda_fecha_hoy_iso,
    }


def serializar_turno_peluqueria(actividad):
    """Turno listo para el Mapa del día y la agenda por profesional."""
    from app.services.peluqueria_turno_estado import COBRADO, ETIQUETAS, estado_turno

    asignacion = actividad.cliente_servicio
    estado = estado_turno(actividad)
    servicio_nombre = asignacion.servicio.nombre if asignacion and asignacion.servicio else ''
    if not servicio_nombre and getattr(actividad, 'servicio', None) is not None:
        servicio_nombre = actividad.servicio.nombre
    return {
        'id': int(actividad.id),
        'titulo': actividad.titulo or 'Turno',
        'cliente_nombre': actividad.cliente.nombre if actividad.cliente else 'Consumidor Final',
        'servicio_nombre': servicio_nombre or actividad.titulo or 'Turno',
        'profesional_nombre': (actividad.usuario.nombre_completo or actividad.usuario.username) if actividad.usuario else 'Sin profesional',
        'hora_inicio': local_strftime(actividad.fecha_inicio, '%H:%M'),
        'hora_fin': local_strftime(actividad.fecha_fin, '%H:%M') if actividad.fecha_fin else '',
        'estado': _ESTADO_VISUAL.get(estado, estado),
        'estado_label': ETIQUETAS.get(estado, estado),
        'cobrado': estado == COBRADO,
    }


# Clases visuales que ya usan el Mapa del día y la agenda del día.
_ESTADO_VISUAL = {
    'agendado': 'pendiente',
    'en_atencion': 'en_atencion',
    'terminado': 'terminado',
    'cobrado': 'hecha',
    'cancelado': 'cancelada',
    'no_show': 'no_show',
}


def obtener_resumen_en_atencion_dashboard(can_ver_agenda, today, usuario=None):
    """Turnos de hoy en atención: con atención iniciada o con su servicio del cliente en proceso."""
    if not can_ver_agenda:
        return {'count': 0, 'items': []}

    start_utc, end_utc = utc_bounds_for_local_dates(today, today)
    query = (
        AgendaActividad.query
        .outerjoin(ClienteServicio, ClienteServicio.id_cliente_servicio == AgendaActividad.cliente_servicio_id)
        .filter(
            AgendaActividad.estado == 'pendiente',
            AgendaActividad.venta_id.is_(None),
            AgendaActividad.fecha_inicio >= start_utc,
            AgendaActividad.fecha_inicio < end_utc,
            or_(AgendaActividad.atencion_inicio.isnot(None), ClienteServicio.estado == 'en_proceso'),
            or_(ClienteServicio.id_venta.is_(None), AgendaActividad.cliente_servicio_id.is_(None)),
        )
    )
    query = _query_agenda_visible(query, usuario=usuario)

    items = (
        query.options(
            joinedload(AgendaActividad.cliente).load_only(Cliente.id_cliente, Cliente.nombre),
            joinedload(AgendaActividad.servicio).load_only(Servicio.id_servicio, Servicio.nombre),
            joinedload(AgendaActividad.cliente_servicio)
            .joinedload(ClienteServicio.servicio)
            .load_only(Servicio.id_servicio, Servicio.nombre),
            noload(AgendaActividad.usuarios_agenda),
            noload(AgendaActividad.usuarios_recordatorio),
        )
        .order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.asc())
        .all()
    )
    return {
        'count': len(items),
        'items': [_serializar_en_atencion(actividad) for actividad in items],
    }


def _serializar_en_atencion(actividad):
    asignacion = actividad.cliente_servicio
    servicio = asignacion.servicio if asignacion is not None and asignacion.servicio else actividad.servicio
    return {
        'id': int(actividad.id),
        'titulo': actividad.titulo or '',
        'hora_label': local_strftime(actividad.fecha_inicio, '%H:%M'),
        'cliente_nombre': actividad.cliente.nombre if actividad.cliente else 'Consumidor Final',
        'servicio_nombre': servicio.nombre if servicio is not None else (actividad.titulo or 'Servicio'),
        'cliente_servicio_id': int(actividad.cliente_servicio_id) if actividad.cliente_servicio_id else None,
        'cobrado': False,
    }
