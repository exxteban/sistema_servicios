"""Mantiene el estado del servicio del cliente en línea con su actividad de agenda."""
from datetime import datetime

from app.models import AgendaActividad


def sincronizar_cliente_servicio_desde_actividad(actividad: AgendaActividad, *, accion: str):
    asignacion = getattr(actividad, 'cliente_servicio', None)
    if asignacion is None:
        return
    estado = (asignacion.estado or '').strip().lower()
    if accion == 'iniciar' and estado in {'solicitado', 'agendado', 'presupuestado'}:
        asignacion.estado = 'en_proceso'
        return
    if accion == 'completar' and estado != 'cancelado':
        asignacion.estado = 'completado'
        if not asignacion.fecha_cierre:
            asignacion.fecha_cierre = datetime.utcnow()
        return
    if accion == 'cancelar' and not getattr(asignacion, 'id_venta', None):
        asignacion.estado = 'cancelado'
        if not asignacion.fecha_cierre:
            asignacion.fecha_cierre = datetime.utcnow()
        return
    if accion == 'reprogramar':
        asignacion.fecha_programada = actividad.fecha_inicio
        if estado in {'solicitado', 'presupuestado', 'cancelado'}:
            asignacion.estado = 'agendado'
            asignacion.fecha_cierre = None
