"""Recordatorios automáticos de turnos por WhatsApp Cloud API.

Solo funcionan si la instalación tiene WhatsApp Cloud API configurado y
`peluqueria_recordatorio_horas_antes` tiene un valor (vacío = desactivado; el botón manual
de "Gestionar turno" sigue disponible siempre). Se intenta una vez por turno.

WhatsApp solo entrega texto libre a quien escribió en las últimas 24 h. Para llegar a
cualquier cliente hay que cargar en `peluqueria_recordatorio_template` el nombre de una
plantilla aprobada por Meta con 4 variables: nombre, servicio, fecha y hora, profesional.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app import db
from app.models import AgendaActividad, Configuracion
from app.services.peluqueria_turno_estado import datos_mensaje_turno, telefono_whatsapp_cliente, texto_mensaje_turno

logger = logging.getLogger(__name__)

CLAVE_HORAS_ANTES = 'peluqueria_recordatorio_horas_antes'
CLAVE_TEMPLATE = 'peluqueria_recordatorio_template'
HORAS_PERMITIDAS = (1, 2, 3, 6, 12, 24, 48)


def whatsapp_configurado() -> bool:
    from app.services.whatsapp.client import _get_config

    config = _get_config()
    return bool(config['dry_run'] or (config['phone_number_id'] and config['access_token']))


def obtener_config_recordatorios() -> dict:
    try:
        horas = int(Configuracion.obtener(CLAVE_HORAS_ANTES, '') or 0)
    except (TypeError, ValueError):
        horas = 0
    return {
        'horas': horas if horas in HORAS_PERMITIDAS else None,
        'template': (Configuracion.obtener(CLAVE_TEMPLATE, '') or '').strip(),
    }


def guardar_config_recordatorios(horas, template) -> str | None:
    """Devuelve un mensaje de error, o None si se guardó."""
    horas = str(horas or '').strip()
    if horas and (not horas.isdigit() or int(horas) not in HORAS_PERMITIDAS):
        return 'Elegí cuántas horas antes mandar el recordatorio.'
    Configuracion.establecer(CLAVE_HORAS_ANTES, horas, 'Peluquería: horas antes del turno para el recordatorio por WhatsApp (vacío = desactivado)')
    Configuracion.establecer(CLAVE_TEMPLATE, (template or '').strip(), 'Peluquería: plantilla de WhatsApp aprobada para recordatorios (vacío = texto)')
    return None


def turnos_para_recordar(ahora_utc: datetime, horas: int) -> list:
    return (
        AgendaActividad.query
        .filter(
            AgendaActividad.tipo == 'cita',
            AgendaActividad.estado == 'pendiente',
            AgendaActividad.atencion_inicio.is_(None),
            AgendaActividad.venta_id.is_(None),
            AgendaActividad.recordatorio_whatsapp_at.is_(None),
            AgendaActividad.cliente_id.isnot(None),
            AgendaActividad.fecha_inicio > ahora_utc,
            AgendaActividad.fecha_inicio <= ahora_utc + timedelta(hours=horas),
        )
        .order_by(AgendaActividad.fecha_inicio.asc())
        .all()
    )


def _enviar(actividad, telefono: str, template: str):
    from app.services.whatsapp import client

    if template:
        datos = datos_mensaje_turno(actividad)
        parametros = [datos['nombre'] or 'cliente', datos['servicio'], f"{datos['fecha']} {datos['hora']}", datos['profesional'] or '-']
        return client.enviar_template(
            telefono,
            template,
            componentes=[{'type': 'body', 'parameters': [{'type': 'text', 'text': valor} for valor in parametros]}],
        )
    return client.enviar_texto(telefono, texto_mensaje_turno(actividad, 'recordatorio'))


def enviar_recordatorios_pendientes(ahora_utc: datetime | None = None) -> dict:
    resumen = {'enviados': 0, 'fallidos': 0, 'sin_telefono': 0}
    config = obtener_config_recordatorios()
    if not config['horas'] or not whatsapp_configurado():
        return resumen
    ahora_utc = ahora_utc or datetime.utcnow()
    for actividad in turnos_para_recordar(ahora_utc, config['horas']):
        actividad.recordatorio_whatsapp_at = ahora_utc
        telefono = telefono_whatsapp_cliente(actividad)
        if not telefono:
            resumen['sin_telefono'] += 1
            continue
        try:
            resultado = _enviar(actividad, telefono, config['template'])
        except Exception:
            logger.exception('Error enviando recordatorio del turno %s', actividad.id)
            resultado = None
        resumen['enviados' if resultado else 'fallidos'] += 1
    db.session.commit()
    return resumen
