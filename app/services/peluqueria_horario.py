"""Horario del local y horarios ocupados para los turnos de peluquería/barbería."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app import db
from app.models import AgendaActividad, Configuracion
from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local


CLAVE_HORA_APERTURA = 'peluqueria_hora_apertura'
CLAVE_HORA_CIERRE = 'peluqueria_hora_cierre'
CLAVE_INTERVALO = 'peluqueria_intervalo_minutos'

HORA_APERTURA_DEFAULT = '08:00'
HORA_CIERRE_DEFAULT = '21:00'
INTERVALO_DEFAULT = 30
INTERVALOS_PERMITIDOS = (10, 15, 20, 30, 45, 60)


def _hora_a_minutos(valor) -> int | None:
    try:
        hora = datetime.strptime(str(valor or '').strip(), '%H:%M')
    except ValueError:
        return None
    return hora.hour * 60 + hora.minute


def _minutos_a_hora(minutos: int) -> str:
    return f'{minutos // 60:02d}:{minutos % 60:02d}'


def _validar_horario(apertura, cierre, intervalo) -> tuple[dict | None, str | None]:
    inicio = _hora_a_minutos(apertura)
    fin = _hora_a_minutos(cierre)
    try:
        intervalo = int(intervalo)
    except (TypeError, ValueError):
        intervalo = None
    if inicio is None or fin is None:
        return None, 'Completá la hora de apertura y de cierre (formato HH:MM).'
    if fin <= inicio:
        return None, 'La hora de cierre tiene que ser posterior a la de apertura.'
    if intervalo not in INTERVALOS_PERMITIDOS:
        return None, 'Elegí un intervalo válido entre turnos.'
    return {
        'apertura': _minutos_a_hora(inicio),
        'cierre': _minutos_a_hora(fin),
        'intervalo': intervalo,
    }, None


def obtener_horario_peluqueria() -> dict:
    """Horario configurado; si falta o es inválido, vuelve al horario de siempre (08:00 a 21:00 cada 30 min)."""
    horario, error = _validar_horario(
        Configuracion.obtener(CLAVE_HORA_APERTURA, HORA_APERTURA_DEFAULT),
        Configuracion.obtener(CLAVE_HORA_CIERRE, HORA_CIERRE_DEFAULT),
        Configuracion.obtener(CLAVE_INTERVALO, INTERVALO_DEFAULT),
    )
    if error:
        return {'apertura': HORA_APERTURA_DEFAULT, 'cierre': HORA_CIERRE_DEFAULT, 'intervalo': INTERVALO_DEFAULT}
    return horario


def guardar_horario_peluqueria(apertura, cierre, intervalo) -> tuple[dict | None, str | None]:
    horario, error = _validar_horario(apertura, cierre, intervalo)
    if error:
        return None, error
    Configuracion.establecer(CLAVE_HORA_APERTURA, horario['apertura'], 'Peluquería: hora de apertura para turnos')
    Configuracion.establecer(CLAVE_HORA_CIERRE, horario['cierre'], 'Peluquería: hora de cierre para turnos')
    Configuracion.establecer(CLAVE_INTERVALO, str(horario['intervalo']), 'Peluquería: minutos entre horarios de turno')
    return horario, None


def horarios_turno_peluqueria(horario: dict | None = None) -> tuple[str, ...]:
    """Horas de inicio de turno, desde la apertura hasta antes del cierre."""
    horario = horario or obtener_horario_peluqueria()
    inicio = _hora_a_minutos(horario['apertura'])
    fin = _hora_a_minutos(horario['cierre'])
    return tuple(_minutos_a_hora(minuto) for minuto in range(inicio, fin, int(horario['intervalo'])))


def query_turnos_solapados(*, profesional_id, fecha_inicio, fecha_fin, excluir_actividad_id=None):
    """Turnos del profesional que ocupan el rango (fechas UTC naive).

    Ocupan los pendientes y también los cobrados por adelantado que todavía no se atendieron
    (el POS los deja en 'hecha' sin `atencion_inicio`). Un turno terminado libera su horario.
    """
    query = AgendaActividad.query.filter(
        AgendaActividad.usuario_id == profesional_id,
        AgendaActividad.tipo == 'cita',
        db.or_(
            AgendaActividad.estado == 'pendiente',
            db.and_(AgendaActividad.estado == 'hecha', AgendaActividad.atencion_inicio.is_(None)),
        ),
        AgendaActividad.fecha_inicio < fecha_fin,
        db.or_(AgendaActividad.fecha_fin.is_(None), AgendaActividad.fecha_fin > fecha_inicio),
    )
    if excluir_actividad_id:
        query = query.filter(AgendaActividad.id != excluir_actividad_id)
    return query


def rangos_ocupados_peluqueria(*, profesional_id: int, fecha: date) -> list[dict]:
    """Rangos ocupados del profesional en el día local, en minutos desde las 00:00."""
    inicio_dia, fin_dia = utc_bounds_for_local_dates(fecha, fecha)
    turnos = (
        query_turnos_solapados(profesional_id=profesional_id, fecha_inicio=inicio_dia, fecha_fin=fin_dia)
        .order_by(AgendaActividad.fecha_inicio.asc(), AgendaActividad.id.asc())
        .all()
    )
    inicio_local_dia = datetime.combine(fecha, datetime.min.time())
    rangos = []
    for turno in turnos:
        inicio = utc_naive_to_local(turno.fecha_inicio).replace(tzinfo=None)
        fin_utc = turno.fecha_fin or (turno.fecha_inicio + timedelta(minutes=INTERVALO_DEFAULT))
        fin = utc_naive_to_local(fin_utc).replace(tzinfo=None)
        inicio_min = max(int((inicio - inicio_local_dia).total_seconds() // 60), 0)
        fin_min = min(int((fin - inicio_local_dia).total_seconds() // 60), 24 * 60)
        if fin_min <= inicio_min:
            continue
        rangos.append({
            'inicio': inicio_min,
            'fin': fin_min,
            'etiqueta': f'{_minutos_a_hora(inicio_min)} a {_minutos_a_hora(min(fin_min, 24 * 60 - 1))}',
        })
    return rangos
