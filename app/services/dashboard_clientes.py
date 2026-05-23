from __future__ import annotations

from datetime import timedelta
from typing import Any

from flask_login import current_user

from app import db
from app.models import AgendaActividad, Venta
from app.services.dashboard_servicios import _filtrar_query_ventas_dashboard_por_sesion
from app.utils.helpers import utc_bounds_for_local_dates


def _build_dashboard_variacion(current: int, previous: int, *, positive_when_higher: bool = True) -> dict[str, Any]:
    current = int(current or 0)
    previous = int(previous or 0)
    diff = current - previous
    if diff == 0:
        return {
            'diff': 0,
            'label': 'Sin cambios vs ayer',
            'class_name': 'text-slate-500 dark:text-slate-400',
        }

    is_positive = (diff > 0) == bool(positive_when_higher)
    return {
        'diff': diff,
        'label': f'{diff:+d} vs ayer',
        'class_name': (
            'text-emerald-600 dark:text-emerald-400'
            if is_positive
            else 'text-rose-600 dark:text-rose-400'
        ),
    }


def _filtrar_agenda_cancelados_por_visibilidad(query):
    from app.routes.agenda.visibilidad import filtro_mostrar_agenda_para_usuario, obtener_root_user_id_sistema

    root_id = obtener_root_user_id_sistema()
    if root_id:
        query = query.filter(AgendaActividad.usuario_id != root_id)
    if not (current_user.es_admin() or current_user.tiene_permiso('agenda_ver_todas')):
        query = query.filter(filtro_mostrar_agenda_para_usuario(current_user.id_usuario))
    return query


def obtener_resumen_clientes_dashboard(
    *,
    today,
    can_ver_agenda: bool,
    puede_ver_otras_cajas: bool,
    sesion_caja_id: int | None,
) -> dict[str, Any]:
    yesterday = today - timedelta(days=1)
    start_today_utc, end_today_utc = utc_bounds_for_local_dates(today, today)
    start_yesterday_utc, end_yesterday_utc = utc_bounds_for_local_dates(yesterday, yesterday)

    ventas_hoy_query = (
        db.session.query(Venta.id_cliente)
        .filter(
            Venta.estado == 'completada',
            Venta.id_cliente.isnot(None),
            Venta.id_cliente != 1,
            Venta.fecha_venta >= start_today_utc,
            Venta.fecha_venta < end_today_utc,
        )
        .distinct()
    )
    ventas_ayer_query = (
        db.session.query(Venta.id_cliente)
        .filter(
            Venta.estado == 'completada',
            Venta.id_cliente.isnot(None),
            Venta.id_cliente != 1,
            Venta.fecha_venta >= start_yesterday_utc,
            Venta.fecha_venta < end_yesterday_utc,
        )
        .distinct()
    )
    ventas_hoy_query = _filtrar_query_ventas_dashboard_por_sesion(
        ventas_hoy_query,
        puede_ver_otras_cajas=puede_ver_otras_cajas,
        sesion_caja_id=sesion_caja_id,
    )
    ventas_ayer_query = _filtrar_query_ventas_dashboard_por_sesion(
        ventas_ayer_query,
        puede_ver_otras_cajas=puede_ver_otras_cajas,
        sesion_caja_id=sesion_caja_id,
    )

    clientes_hoy = {int(cliente_id) for (cliente_id,) in ventas_hoy_query.all() if cliente_id}
    clientes_ayer = {int(cliente_id) for (cliente_id,) in ventas_ayer_query.all() if cliente_id}
    clientes_considerados = sorted(clientes_hoy | clientes_ayer)

    primera_venta_por_cliente = {}
    if clientes_considerados:
        rows = (
            db.session.query(
                Venta.id_cliente,
                db.func.min(Venta.fecha_venta).label('primera_fecha'),
            )
            .filter(
                Venta.estado == 'completada',
                Venta.id_cliente.in_(clientes_considerados),
            )
            .group_by(Venta.id_cliente)
            .all()
        )
        primera_venta_por_cliente = {
            int(cliente_id): primera_fecha
            for cliente_id, primera_fecha in rows
            if cliente_id and primera_fecha
        }

    nuevos_hoy = sum(
        1
        for cliente_id in clientes_hoy
        if start_today_utc <= primera_venta_por_cliente.get(cliente_id) < end_today_utc
    )
    nuevos_ayer = sum(
        1
        for cliente_id in clientes_ayer
        if start_yesterday_utc <= primera_venta_por_cliente.get(cliente_id) < end_yesterday_utc
    )

    cancelados_hoy = 0
    cancelados_ayer = 0
    if can_ver_agenda:
        cancelados_hoy_query = db.session.query(db.func.count(db.distinct(AgendaActividad.cliente_id))).filter(
            AgendaActividad.tipo == 'cita',
            AgendaActividad.estado == 'cancelada',
            AgendaActividad.cliente_id.isnot(None),
            AgendaActividad.fecha_inicio >= start_today_utc,
            AgendaActividad.fecha_inicio < end_today_utc,
        )
        cancelados_ayer_query = db.session.query(db.func.count(db.distinct(AgendaActividad.cliente_id))).filter(
            AgendaActividad.tipo == 'cita',
            AgendaActividad.estado == 'cancelada',
            AgendaActividad.cliente_id.isnot(None),
            AgendaActividad.fecha_inicio >= start_yesterday_utc,
            AgendaActividad.fecha_inicio < end_yesterday_utc,
        )
        cancelados_hoy = int(_filtrar_agenda_cancelados_por_visibilidad(cancelados_hoy_query).scalar() or 0)
        cancelados_ayer = int(_filtrar_agenda_cancelados_por_visibilidad(cancelados_ayer_query).scalar() or 0)

    total_hoy = len(clientes_hoy)
    total_ayer = len(clientes_ayer)
    recurrentes_hoy = max(total_hoy - nuevos_hoy, 0)
    recurrentes_ayer = max(total_ayer - nuevos_ayer, 0)

    return {
        'nuevos': {
            'count': nuevos_hoy,
            **_build_dashboard_variacion(nuevos_hoy, nuevos_ayer, positive_when_higher=True),
        },
        'recurrentes': {
            'count': recurrentes_hoy,
            **_build_dashboard_variacion(recurrentes_hoy, recurrentes_ayer, positive_when_higher=True),
        },
        'cancelados': {
            'count': cancelados_hoy,
            **_build_dashboard_variacion(cancelados_hoy, cancelados_ayer, positive_when_higher=False),
        },
        'total_count': total_hoy,
        'total_variacion': _build_dashboard_variacion(total_hoy, total_ayer, positive_when_higher=True),
    }
