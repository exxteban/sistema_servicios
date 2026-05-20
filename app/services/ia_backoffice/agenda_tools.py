from sqlalchemy import func

from app import db
from app.models import AgendaActividad
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.utils.helpers import utc_bounds_for_local_dates


def _base_agenda(desde, hasta):
    inicio, fin = utc_bounds_for_local_dates(desde, hasta)
    return AgendaActividad.query.filter(
        AgendaActividad.fecha_inicio >= inicio,
        AgendaActividad.fecha_inicio < fin,
    )


def _item_actividad(item: AgendaActividad) -> dict:
    return {
        'id': item.id,
        'tipo': item.tipo,
        'titulo': item.titulo,
        'estado': item.estado,
        'prioridad': item.prioridad,
        'fecha_inicio': item.fecha_inicio.isoformat() if item.fecha_inicio else None,
        'usuario': item.usuario.username if item.usuario else None,
        'cliente': item.cliente.nombre if item.cliente else None,
        'origen_modulo': item.origen_modulo,
    }


def turnos_resumen(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    base = _base_agenda(rango['desde'], rango['hasta'])
    por_estado = [
        {'estado': row.estado or 'sin_estado', 'cantidad': int(row.cantidad or 0)}
        for row in base.with_entities(AgendaActividad.estado, func.count(AgendaActividad.id).label('cantidad'))
        .group_by(AgendaActividad.estado).all()
    ]
    por_tipo = [
        {'tipo': row.tipo or 'sin_tipo', 'cantidad': int(row.cantidad or 0)}
        for row in base.with_entities(AgendaActividad.tipo, func.count(AgendaActividad.id).label('cantidad'))
        .group_by(AgendaActividad.tipo).all()
    ]
    return {**rango, 'cantidad_actividades': int(base.count()), 'por_estado': por_estado, 'por_tipo': por_tipo}


def turnos_proximos(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args or {'periodo': '7d'})
    top_n = normalizar_top_n(args.get('top_n'), default=10)
    filas = (
        _base_agenda(rango['desde'], rango['hasta'])
        .filter(AgendaActividad.estado.in_(['pendiente', 'confirmado', 'programado']))
        .order_by(AgendaActividad.fecha_inicio.asc())
        .limit(top_n)
        .all()
    )
    return {**rango, 'turnos': [_item_actividad(item) for item in filas]}


def turnos_cancelados(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n(args.get('top_n'), default=10)
    filas = (
        _base_agenda(rango['desde'], rango['hasta'])
        .filter(AgendaActividad.estado.in_(['cancelado', 'cancelada']))
        .order_by(AgendaActividad.fecha_inicio.desc())
        .limit(top_n)
        .all()
    )
    return {**rango, 'cantidad_cancelados': len(filas), 'turnos': [_item_actividad(item) for item in filas]}


def atenciones_resumen(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    base = _base_agenda(rango['desde'], rango['hasta']).filter(
        db.or_(
            AgendaActividad.tipo.ilike('%atencion%'),
            AgendaActividad.origen_modulo.ilike('%atencion%'),
            AgendaActividad.origen_modulo.ilike('%odontologia%'),
            AgendaActividad.origen_modulo.ilike('%veterinaria%'),
        )
    )
    return {
        **rango,
        'cantidad_atenciones_agendadas': int(base.count()),
        'por_estado': [
            {'estado': row.estado or 'sin_estado', 'cantidad': int(row.cantidad or 0)}
            for row in base.with_entities(AgendaActividad.estado, func.count(AgendaActividad.id).label('cantidad'))
            .group_by(AgendaActividad.estado).all()
        ],
        'nota': 'Resumen basado en agenda_actividades; no modifica turnos ni atenciones.',
    }
