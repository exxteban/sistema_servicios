"""Guarda de anulacion por factura electronica, compartida por ventas y gastronomia.

No se puede anular una venta con factura electronica viva: quedaria declarado
ante SIFEN un ingreso que no existio. Primero se cancela el DE (evento con
motivo, dentro de las 48h) o se emite la nota de credito de anulacion.
"""

MENSAJE_FE_VIGENTE = (
    'Esta venta tiene una factura electrónica vigente en SIFEN. Cancelá primero '
    'la factura electrónica (con su motivo) y después anulá la venta. Si ya '
    'pasaron las 48h, SIFEN no permite cancelar: corresponde emitir la nota de '
    'crédito de anulación.'
)


def error_anulacion_por_factura_electronica(venta):
    """Devuelve el mensaje de bloqueo, o None si la venta se puede anular."""
    from facturacion_electronica.services import obtener_documento
    from facturacion_electronica.services.guarda import documento_impide_anular_venta

    if documento_impide_anular_venta(obtener_documento(venta.id_venta)):
        return MENSAJE_FE_VIGENTE
    return None
