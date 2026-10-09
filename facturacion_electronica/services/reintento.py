"""Reintentar la emisión de un DE que falló, en un solo paso.

Con la API, `emitir` ya es el reintento completo (`correct/` y reenvío). Con
el motor propio, `emitir` sólo regenera, firma y arma el QR, y deja el envío
al job: en la venta nueva está bien —el POS no espera a SIFEN—, pero a quien
aprieta "Reintentar" sobre una rechazada le debe una respuesta ahora, no en la
próxima pasada.

Regenerar no quema otro número: `generar_documento` conserva el número y el
código de seguridad, así que el CDC es el mismo del intento anterior.
"""
from facturacion_electronica import ESTADO_ERROR, ESTADO_RECHAZADO
from facturacion_electronica.services.emision_service import obtener_documento
from facturacion_electronica.services.proveedores.fachada import (
    capacidades,
    emitir_para_pos,
    enviar_documento,
)

ESTADOS_REINTENTABLES = (ESTADO_RECHAZADO, ESTADO_ERROR)


def puede_reintentar(documento, venta):
    """True si el DE falló y su número todavía se puede reenviar."""
    from facturacion_electronica.services.acciones import _numero_definitivamente_perdido

    if documento is None or venta is None or documento.estado not in ESTADOS_REINTENTABLES:
        return False
    return not _numero_definitivamente_perdido(documento, venta)


def emitir_o_reintentar(venta):
    """Emite la venta; si ya tenía un DE fallido, lo reenvía. Devuelve (doc, error)."""
    previo = obtener_documento(venta.id_venta)
    reintento = previo is not None and previo.estado in ESTADOS_REINTENTABLES

    documento, error = emitir_para_pos(venta)
    if error or not reintento or not capacidades()['herramientas_propias']:
        return documento, error
    return enviar_documento(documento)
