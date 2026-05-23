from flask import jsonify, request
from flask_login import current_user, login_required
from sqlalchemy.orm import load_only

from app.models import AgendaActividad
from app.routes.agenda import agenda_bp
from app.routes.agenda.actividades import (
    _construir_query_lista_actividades,
    _filtro_recordatorio_para_usuario,
    _parse_user_ids_list,
    _proximo_cambio_alerta_actividad,
    _resolver_estado_alerta,
    _resolver_filtros_lista_actividades,
    _serializar_alerta_actividad,
    _utc_now_naive,
)


@agenda_bp.route('/api/alertas/resumen', methods=['GET'])
@login_required
def resumen_alertas():
    now_utc = _utc_now_naive()
    limit = min(max(request.args.get('limit', 50, type=int), 1), 200)
    actividades = (
        AgendaActividad.query
        .options(
            load_only(
                AgendaActividad.id,
                AgendaActividad.titulo,
                AgendaActividad.tipo,
                AgendaActividad.prioridad,
                AgendaActividad.estado,
                AgendaActividad.fecha_inicio,
                AgendaActividad.fecha_fin,
                AgendaActividad.recordatorio_minutos,
            )
        )
        .filter(AgendaActividad.estado == 'pendiente')
        .filter(_filtro_recordatorio_para_usuario(current_user.id_usuario))
        .order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.desc())
        .all()
    )

    alert_items = []
    total_count = overdue_count = alert_count = 0
    next_check_at = None
    for actividad in actividades:
        next_change_at = _proximo_cambio_alerta_actividad(actividad, now_utc=now_utc)
        if next_change_at and (next_check_at is None or next_change_at < next_check_at):
            next_check_at = next_change_at
        item = _serializar_alerta_actividad(actividad, now_utc=now_utc)
        if not item:
            continue
        total_count += 1
        if item['estado_alerta'] == 'overdue':
            overdue_count += 1
        elif item['estado_alerta'] == 'alert':
            alert_count += 1
        alert_items.append(item)

    alert_items.sort(
        key=lambda item: (
            0 if item.get('estado_alerta') == 'overdue' else 1,
            item.get('trigger_at_utc') or item.get('fecha_inicio_utc') or '',
            str(item.get('titulo') or '').lower(),
            item.get('id') or 0,
        )
    )
    return jsonify(
        {
            'count': total_count,
            'has_alerts': total_count > 0,
            'overdue_count': overdue_count,
            'alert_count': alert_count,
            'server_time_utc': f'{now_utc.isoformat()}Z',
            'next_check_at_utc': f'{next_check_at.isoformat()}Z' if next_check_at else None,
            'items': alert_items[:limit],
        }
    )


@agenda_bp.route('/api/actividades/estado', methods=['GET'])
@login_required
def estado_actividades_lista():
    filtros = _resolver_filtros_lista_actividades()
    page = filtros['page']
    ids = _parse_user_ids_list(request.args.getlist('ids'))
    now_utc = _utc_now_naive()
    query_base = _construir_query_lista_actividades(filtros, include_options=False, include_sort=False)
    actividades_pagina = (
        _construir_query_lista_actividades(filtros, include_options=False)
        .options(load_only(AgendaActividad.id))
        .paginate(page=page, per_page=25, error_out=False)
    )
    page_ids = [actividad.id for actividad in actividades_pagina.items]
    query_ids = ids if ids else page_ids

    if not query_ids:
        return jsonify(
            {
                'items': [],
                'missing_ids': [],
                'page_ids': page_ids,
                'page': actividades_pagina.page,
                'pages': actividades_pagina.pages,
                'total': actividades_pagina.total,
                'server_time_utc': f'{now_utc.isoformat()}Z',
            }
        )

    actividades = (
        query_base
        .options(
            load_only(
                AgendaActividad.id,
                AgendaActividad.estado,
                AgendaActividad.fecha_inicio,
                AgendaActividad.fecha_fin,
                AgendaActividad.recordatorio_minutos,
                AgendaActividad.updated_at,
            )
        )
        .filter(AgendaActividad.id.in_(query_ids))
        .all()
    )
    visibles = {actividad.id for actividad in actividades}
    return jsonify(
        {
            'items': [
                {
                    'id': actividad.id,
                    'estado': actividad.estado,
                    'estado_alerta': _resolver_estado_alerta(actividad, now_utc=now_utc),
                    'updated_at_utc': f'{actividad.updated_at.isoformat()}Z' if actividad.updated_at else None,
                }
                for actividad in actividades
            ],
            'missing_ids': [actividad_id for actividad_id in query_ids if actividad_id not in visibles],
            'page_ids': page_ids,
            'page': actividades_pagina.page,
            'pages': actividades_pagina.pages,
            'total': actividades_pagina.total,
            'server_time_utc': f'{now_utc.isoformat()}Z',
        }
    )
