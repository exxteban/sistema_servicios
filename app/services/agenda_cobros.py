from __future__ import annotations

from app.models import AgendaActividad


def _parse_positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _marcar_actividad_cobrada(actividad, venta):
    if actividad is None or venta is None:
        return None
    if actividad.venta_id:
        return actividad
    if actividad.cliente_id and venta.id_cliente and int(actividad.cliente_id) != int(venta.id_cliente):
        return None

    actividad.venta_id = int(venta.id_venta)
    if (actividad.estado or '').strip().lower() != 'cancelada':
        actividad.estado = 'hecha'
    return actividad


def vincular_venta_a_agenda_cobrada(*, venta, agenda_actividad_id=None, cliente_servicio_objs=None):
    actividad_id = _parse_positive_int(agenda_actividad_id)
    if actividad_id:
        _marcar_actividad_cobrada(AgendaActividad.query.filter_by(id=actividad_id).first(), venta)

    cliente_servicio_ids = [
        int(asignacion.id_cliente_servicio)
        for asignacion in (cliente_servicio_objs or [])
        if getattr(asignacion, 'id_cliente_servicio', None)
    ]
    if not cliente_servicio_ids:
        return

    actividades = (
        AgendaActividad.query
        .filter(
            AgendaActividad.cliente_servicio_id.in_(cliente_servicio_ids),
            AgendaActividad.venta_id.is_(None),
        )
        .all()
    )
    for actividad in actividades:
        _marcar_actividad_cobrada(actividad, venta)
