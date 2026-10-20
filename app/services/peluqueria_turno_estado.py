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


def telefono_whatsapp_cliente(actividad) -> str | None:
    """Teléfono del cliente del turno en formato internacional sin '+', o None."""
    cliente = getattr(actividad, 'cliente', None)
    telefono = normalizar_telefono(getattr(cliente, 'telefono', None) or '') if cliente else None
    return telefono.lstrip('+') if telefono else None


def datos_mensaje_turno(actividad) -> dict:
    cliente = getattr(actividad, 'cliente', None)
    return {
        'nombre': ((cliente.nombre or '').split() or [''])[0] if cliente else '',
        'servicio': _servicio_nombre(actividad),
        'fecha': local_strftime(actividad.fecha_inicio, '%d/%m'),
        'hora': local_strftime(actividad.fecha_inicio, '%H:%M'),
        'profesional': (actividad.usuario.nombre_completo or actividad.usuario.username) if actividad.usuario else '',
    }


def texto_mensaje_turno(actividad, tipo: str) -> str:
    datos = datos_mensaje_turno(actividad)
    cuando = f"el {datos['fecha']} a las {datos['hora']}"
    con = f" con {datos['profesional']}" if datos['profesional'] else ''
    saludo = f"Hola {datos['nombre']}!" if datos['nombre'] else 'Hola!'
    if tipo == 'recordatorio':
        return f"{saludo} Te recordamos tu turno de {datos['servicio']} {cuando}{con}. Te esperamos."
    return f"{saludo} Te confirmamos tu turno de {datos['servicio']} {cuando}{con}. Cualquier cambio, avisanos por acá."


def enlace_whatsapp_turno(actividad, tipo: str) -> str | None:
    """Enlace wa.me con el mensaje armado. No envía nada: lo abre quien atiende."""
    telefono = telefono_whatsapp_cliente(actividad)
    if not telefono:
        return None
    return f"https://wa.me/{telefono}?text={quote(texto_mensaje_turno(actividad, tipo))}"
