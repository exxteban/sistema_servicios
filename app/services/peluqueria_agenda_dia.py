"""Agenda del día de peluquería/barbería: una columna por profesional y una fila por horario."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import joinedload, noload

from app.models import AgendaActividad, ClienteServicio
from app.services.dashboard_agenda import serializar_turno_peluqueria
from app.services.peluqueria_horario import obtener_horario_peluqueria
from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local


def _minutos_locales(valor_utc, dia: date) -> int | None:
    if valor_utc is None:
        return None
    local = utc_naive_to_local(valor_utc).replace(tzinfo=None)
    return int((local - datetime.combine(dia, datetime.min.time())).total_seconds() // 60)


def _hora(minutos: int) -> str:
    return f'{minutos // 60:02d}:{minutos % 60:02d}'


def _rango_grilla(horario: dict, turnos: list[dict], intervalo: int) -> tuple[int, int]:
    """Horario del local, ampliado si hay turnos fuera de él, alineado al intervalo."""
    apertura = int(horario['apertura'][:2]) * 60 + int(horario['apertura'][3:])
    cierre = int(horario['cierre'][:2]) * 60 + int(horario['cierre'][3:])
    inicio = min([apertura] + [turno['inicio_min'] for turno in turnos])
    fin = max([cierre] + [turno['fin_min'] for turno in turnos])
    inicio = max(inicio - (inicio - apertura) % intervalo, 0)
    fin = min(fin + (-(fin - inicio)) % intervalo, 24 * 60)
    return inicio, fin


def construir_agenda_dia(*, dia: date, profesionales: list, query_turnos) -> dict:
    """Arma la grilla del día.

    `profesionales`: usuarios visibles para quien mira. `query_turnos`: consulta de citas ya
    filtrada por visibilidad; acá se limita al día y a esos profesionales.
    """
    horario = obtener_horario_peluqueria()
    intervalo = int(horario['intervalo'])
    ids = [int(usuario.id_usuario) for usuario in profesionales]
    inicio_utc, fin_utc = utc_bounds_for_local_dates(dia, dia)
    actividades = []
    if ids:
        actividades = (
            query_turnos
            .options(
                joinedload(AgendaActividad.usuario),
                joinedload(AgendaActividad.cliente),
                joinedload(AgendaActividad.cliente_servicio).joinedload(ClienteServicio.servicio),
                noload(AgendaActividad.usuarios_agenda),
                noload(AgendaActividad.usuarios_recordatorio),
            )
            .filter(
                AgendaActividad.usuario_id.in_(ids),
                AgendaActividad.fecha_inicio >= inicio_utc,
                AgendaActividad.fecha_inicio < fin_utc,
            )
            .order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.asc())
            .all()
        )

    turnos, cerrados = [], []
    for actividad in actividades:
        turno = serializar_turno_peluqueria(actividad)
        inicio_min = max(_minutos_locales(actividad.fecha_inicio, dia), 0)
        fin_min = _minutos_locales(actividad.fecha_fin, dia) if actividad.fecha_fin else inicio_min + intervalo
        turno.update({
            'profesional_id': int(actividad.usuario_id),
            'inicio_min': inicio_min,
            'fin_min': min(max(fin_min, inicio_min + 10), 24 * 60),
        })
        (cerrados if turno['estado'] in {'cancelada', 'no_show'} else turnos).append(turno)

    inicio, fin = _rango_grilla(horario, turnos, intervalo)
    return {
        'fecha': dia,
        'intervalo': intervalo,
        'inicio_min': inicio,
        'filas': [{'minuto': minuto, 'hora': _hora(minuto)} for minuto in range(inicio, fin, intervalo)],
        'columnas': [
            {
                'id': int(usuario.id_usuario),
                'nombre': usuario.nombre_completo or usuario.username,
                'turnos': [turno for turno in turnos if turno['profesional_id'] == int(usuario.id_usuario)],
            }
            for usuario in profesionales
        ],
        'cerrados': cerrados,
        'total_turnos': len(turnos),
    }
