from flask import render_template
from flask_login import login_required, current_user
from sqlalchemy import and_, case

from app import db
from app.models import AgendaActividad
from app.routes.agenda.actividades import _filtro_mostrar_agenda_para_usuario
from app.routes.agenda import agenda_bp
from app.utils.perf import perf_section
from app.utils.helpers import today_local, utc_bounds_for_local_dates

PRIORIDADES_ACTIVIDAD = ('baja', 'media', 'alta', 'critica')


@agenda_bp.route('/', methods=['GET'])
@agenda_bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    today = today_local()
    start_utc, end_utc = utc_bounds_for_local_dates(today, today)
    pending_query = AgendaActividad.query.filter(AgendaActividad.estado == 'pendiente')

    if not (current_user.es_admin() or current_user.tiene_permiso('agenda_ver_todas')):
        filtro_visible = _filtro_mostrar_agenda_para_usuario(current_user.id_usuario)
        pending_query = pending_query.filter(filtro_visible)

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

    return render_template(
        'agenda/dashboard.html',
        pendientes_hoy=pendientes_hoy,
        vencidas=vencidas,
        proximas=proximas,
        prioridades_pendientes=prioridades_pendientes,
        fecha_hoy=today,
    )
