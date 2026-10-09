"""Evento de cancelación de un DE aprobado, contra la API externa.

Vive aparte de `api.py` por el límite de 600 líneas, con la misma forma que
`api_inutilizacion`: recibe el `refrescar` del proveedor para releer el
documento después del evento.
"""
from datetime import datetime, timedelta

from app import db
from facturacion_electronica import (
    ESTADO_API_CANCELACION_PENDIENTE,
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
)
from facturacion_electronica.services.emision_service import (
    HORAS_LIMITE_CANCELACION,
    fecha_emision,
)
from facturacion_electronica.services.proveedores import api_client
from facturacion_electronica.services.proveedores.api_documento import serializar


def cancelar_documento(config, documento, motivo, refrescar):
    """Pide la cancelación en SIFEN. Devuelve (documento, error)."""
    if documento is None:
        return documento, 'No hay documento para cancelar.'
    if documento.estado == ESTADO_CANCELADO:
        return documento, 'El documento ya está cancelado.'
    if documento.estado != ESTADO_APROBADO:
        return documento, 'Sólo se puede cancelar en SIFEN un documento aprobado.'
    if not documento.api_documento_id:
        return documento, 'El documento no tiene identificador en la API; no se puede cancelar.'

    motivo = (motivo or '').strip()
    if not 5 <= len(motivo) <= 500:
        return documento, 'El motivo de cancelación debe tener entre 5 y 500 caracteres.'

    referencia = fecha_emision(documento)
    if referencia and datetime.utcnow() - referencia > timedelta(hours=HORAS_LIMITE_CANCELACION):
        return documento, (
            f'Pasaron más de {HORAS_LIMITE_CANCELACION}h desde la emisión; SIFEN ya no '
            'permite cancelar. Corresponde emitir una nota de crédito.'
        )

    evento, error = api_client.solicitar(
        config, 'POST',
        f'/sifen/electronic-documents/{documento.api_documento_id}/cancel/',
        json={'motive': motivo},
        timeout=api_client.TIMEOUT_EMISION_SEGUNDOS,
    )
    if error:
        return documento, error

    documento.motivo_cancelacion = motivo
    documento.respuesta_raw = serializar(evento)
    documento.respuesta_codigo = ESTADO_API_CANCELACION_PENDIENTE
    db.session.commit()

    _documento, error_refresco = refrescar(documento)
    if error_refresco and documento.estado != ESTADO_CANCELADO:
        documento.respuesta_codigo = ESTADO_API_CANCELACION_PENDIENTE
        documento.motivo_cancelacion = motivo
        db.session.commit()
    elif documento.estado != ESTADO_CANCELADO:
        documento.motivo_cancelacion = motivo
        db.session.commit()
    return documento, None


__all__ = ['cancelar_documento']
