from flask_login import current_user
from sqlalchemy import and_, case
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
                ),
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
                AgendaActividad.venta_id.is_(None),
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
        'turnero_actividades': [_serializar_turnero_actividad(actividad) for actividad in turnero_items],
        'fecha_hoy_iso': agenda_fecha_hoy_iso,
    }


def _serializar_turnero_actividad(actividad):
    asignacion = actividad.cliente_servicio
    estado = (actividad.estado or '').strip().lower() or 'pendiente'
    asignacion_estado = (asignacion.estado or '').strip().lower() if asignacion else ''
    no_show = 'no-show' in ((actividad.observaciones or '').lower())
    estado_visual = 'no_show' if no_show else ('en_atencion' if asignacion_estado == 'en_proceso' else estado)
    servicio_nombre = asignacion.servicio.nombre if asignacion and asignacion.servicio else ''
    return {
        'id': int(actividad.id),
        'titulo': actividad.titulo or 'Turno',
        'cliente_nombre': actividad.cliente.nombre if actividad.cliente else 'Consumidor Final',
        'servicio_nombre': servicio_nombre or actividad.titulo or 'Turno',
        'profesional_nombre': (actividad.usuario.nombre_completo or actividad.usuario.username) if actividad.usuario else 'Sin profesional',
        'hora_inicio': local_strftime(actividad.fecha_inicio, '%H:%M'),
        'hora_fin': local_strftime(actividad.fecha_fin, '%H:%M') if actividad.fecha_fin else '',
        'estado': estado_visual,
        'estado_label': _turnero_estado_label(estado_visual),
        'cobrado': bool(asignacion and asignacion.id_venta),
    }


def _turnero_estado_label(estado):
    labels = {
        'pendiente': 'Agendado',
        'en_atencion': 'En atención',
        'hecha': 'Finalizado',
        'cancelada': 'Cancelado',
        'no_show': 'No-show',
    }
    return labels.get(estado, estado.replace('_', ' ').title())


def obtener_resumen_en_atencion_dashboard(can_ver_agenda, today, usuario=None):
    if not can_ver_agenda:
        return {'count': 0, 'items': []}

    start_utc, end_utc = utc_bounds_for_local_dates(today, today)
    query = (
        AgendaActividad.query
        .join(ClienteServicio, ClienteServicio.id_cliente_servicio == AgendaActividad.cliente_servicio_id)
        .filter(
            AgendaActividad.estado == 'pendiente',
            AgendaActividad.fecha_inicio >= start_utc,
            AgendaActividad.fecha_inicio < end_utc,
            ClienteServicio.estado == 'en_proceso',
        )
    )
    query = _query_agenda_visible(query, usuario=usuario)

    items = (
        query.options(
            load_only(
                AgendaActividad.id,
                AgendaActividad.titulo,
                AgendaActividad.fecha_inicio,
                AgendaActividad.cliente_servicio_id,
            ),
            joinedload(AgendaActividad.cliente_servicio).load_only(
                ClienteServicio.id_cliente_servicio,
                ClienteServicio.id_cliente,
                ClienteServicio.id_servicio,
                ClienteServicio.id_venta,
                ClienteServicio.estado,
                ClienteServicio.precio_pactado,
                ClienteServicio.cantidad,
            ).joinedload(ClienteServicio.cliente).load_only(Cliente.id_cliente, Cliente.nombre),
            joinedload(AgendaActividad.cliente_servicio)
            .joinedload(ClienteServicio.servicio)
            .load_only(Servicio.id_servicio, Servicio.nombre),
        )
        .order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.asc())
        .all()
    )
    return {
        'count': len(items),
        'items': [
            {
                'id': int(actividad.id),
                'titulo': actividad.titulo or '',
                'hora_label': local_strftime(actividad.fecha_inicio, '%H:%M'),
                'cliente_nombre': (actividad.cliente_servicio.cliente.nombre if actividad.cliente_servicio and actividad.cliente_servicio.cliente else 'Consumidor Final'),
                'servicio_nombre': (actividad.cliente_servicio.servicio.nombre if actividad.cliente_servicio and actividad.cliente_servicio.servicio else 'Servicio'),
                'cliente_servicio_id': int(actividad.cliente_servicio_id) if actividad.cliente_servicio_id else None,
                'cobrado': bool(actividad.cliente_servicio and actividad.cliente_servicio.id_venta),
            }
            for actividad in items
        ],
    }
