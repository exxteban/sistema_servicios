"""Estados de un turno de peluquería: Agendado → En atención → Terminado → Cobrado."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from app.services.agenda_cliente_servicio_sync import sincronizar_cliente_servicio_desde_actividad
from app.services.peluqueria_senas import turno_ya_cobrado
from app.utils.helpers import local_strftime
from app.utils.phone_utils import normalizar_telefono


AGENDADO = 'agendado'
EN_ATENCION = 'en_atencion'
TERMINADO = 'terminado'
COBRADO = 'cobrado'
CANCELADO = 'cancelado'
NO_SHOW = 'no_show'

ETIQUETAS = {
    AGENDADO: 'Agendado',
    EN_ATENCION: 'En atención',
    TERMINADO: 'Terminado',
    COBRADO: 'Cobrado',
    CANCELADO: 'Cancelado',
    NO_SHOW: 'No-show',
}
PASOS = (AGENDADO, EN_ATENCION, TERMINADO, COBRADO)


def es_no_show(actividad) -> bool:
    motivo = (getattr(actividad, 'cierre_motivo', None) or '').strip().lower()
    if motivo:
        return motivo == NO_SHOW
    # Turnos cerrados antes de existir cierre_motivo: el no-show quedaba solo en las notas.
    return 'no-show' in (actividad.observaciones or '').lower()


def estado_turno(actividad) -> str:
    estado = (actividad.estado or '').strip().lower()
    if estado == 'cancelada':
        return NO_SHOW if es_no_show(actividad) else CANCELADO
    if turno_ya_cobrado(actividad):
        return COBRADO
    if estado == 'hecha':
        return TERMINADO
    asignacion = getattr(actividad, 'cliente_servicio', None)
    asignacion_estado = (asignacion.estado or '').strip().lower() if asignacion is not None else ''
    if getattr(actividad, 'atencion_inicio', None) or asignacion_estado == 'en_proceso':
        return EN_ATENCION
    return AGENDADO


def marcar_inicio_atencion(actividad) -> None:
    if actividad.tipo == 'cita' and getattr(actividad, 'atencion_inicio', None) is None:
        actividad.atencion_inicio = datetime.utcnow()


def empezar_atencion(actividad) -> str | None:
    """Devuelve un mensaje de error, o None si se pudo."""
    if estado_turno(actividad) != AGENDADO:
        return 'Este turno ya no está agendado: no se puede empezar la atención.'
    marcar_inicio_atencion(actividad)
    sincronizar_cliente_servicio_desde_actividad(actividad, accion='iniciar')
    return None


def terminar_turno(actividad) -> str | None:
    if estado_turno(actividad) not in {AGENDADO, EN_ATENCION}:
        return 'Este turno ya está terminado o cerrado.'
    marcar_inicio_atencion(actividad)
    actividad.estado = 'hecha'
    sincronizar_cliente_servicio_desde_actividad(actividad, accion='completar')
    return None


def _servicio_nombre(actividad) -> str:
    asignacion = getattr(actividad, 'cliente_servicio', None)
    if asignacion is not None and asignacion.servicio is not None:
        return asignacion.servicio.nombre
    if getattr(actividad, 'servicio', None) is not None:
        return actividad.servicio.nombre
    return actividad.titulo or 'tu turno'


def enlace_whatsapp_turno(actividad, tipo: str) -> str | None:
    """Enlace wa.me con el mensaje armado. No envía nada: lo abre quien atiende."""
    cliente = getattr(actividad, 'cliente', None)
    telefono = normalizar_telefono(getattr(cliente, 'telefono', None) or '') if cliente else None
    if not telefono:
        return None
    nombre = (cliente.nombre or '').split()[0] if cliente.nombre else ''
    profesional = actividad.usuario.nombre_completo or actividad.usuario.username if actividad.usuario else ''
    cuando = f"el {local_strftime(actividad.fecha_inicio, '%d/%m')} a las {local_strftime(actividad.fecha_inicio, '%H:%M')}"
    con = f' con {profesional}' if profesional else ''
    saludo = f'Hola {nombre}!' if nombre else 'Hola!'
    if tipo == 'recordatorio':
        texto = f'{saludo} Te recordamos tu turno de {_servicio_nombre(actividad)} {cuando}{con}. Te esperamos.'
    else:
        texto = f'{saludo} Te confirmamos tu turno de {_servicio_nombre(actividad)} {cuando}{con}. Cualquier cambio, avisanos por acá.'
    return f"https://wa.me/{telefono.lstrip('+')}?text={quote(texto)}"
