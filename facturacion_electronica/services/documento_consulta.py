"""Lectura de los documentos electrónicos guardados: cuál es la factura
vigente de una venta, sus notas de crédito, el CDC y la fecha de emisión."""
import re

from app import db
from facturacion_electronica import TIPO_FACTURA, TIPO_NOTA_CREDITO
from facturacion_electronica.models import DocumentoElectronico


_CDC_RE = re.compile(r'<DE\s+Id="(\d+)"')


def fecha_emision(documento):
    """Fecha de emisión (dFeEmiDE) del documento: la de la venta, no la de generación
    del XML. SIFEN cuenta las ventanas de envío/cancelación desde esa fecha.
    getattr defensivo: si la venta ya no está disponible, cae a las fechas
    guardadas en el propio documento.

    La nota de crédito es la excepción: se emite hoy para corregir una factura
    que puede ser de hace meses. Contra la fecha de la venta, la ventana de
    72h nacía vencida y la NC no se podía enviar nunca.
    """
    if documento is None:
        return None
    if getattr(documento, 'tipo_documento', None) == TIPO_NOTA_CREDITO:
        return (getattr(documento, 'fecha_generado', None)
                or getattr(documento, 'fecha_envio', None))
    venta = getattr(documento, 'venta', None)
    if venta is not None and getattr(venta, 'fecha_venta', None):
        return venta.fecha_venta
    return getattr(documento, 'fecha_generado', None) or getattr(documento, 'fecha_envio', None)


def extraer_cdc(xml):
    if not xml:
        return None
    match = _CDC_RE.search(xml)
    return match.group(1) if match else None


def obtener_documento(venta_id):
    """Devuelve la **factura** vigente de la venta: la más reciente (mayor id).

    Las notas de crédito cuelgan de la misma venta; si entraran acá, la última
    NC pasaría a ser "el documento" de la venta y el POS, el KuDE y la guarda
    de anulación empezarían a mirar el documento equivocado. El tipo nulo es de
    los documentos viejos, anteriores a las notas de crédito: son facturas.
    """
    return (
        DocumentoElectronico.query
        .filter(
            DocumentoElectronico.id_venta == venta_id,
            db.or_(
                DocumentoElectronico.tipo_documento.is_(None),
                DocumentoElectronico.tipo_documento == TIPO_FACTURA,
            ),
        )
        .order_by(DocumentoElectronico.id.desc())
        .first()
    )


def facturas_de_ventas(venta_ids):
    """{id_venta: factura vigente} para un listado. Una sola consulta.

    Existe para que la pantalla de Historial de Ventas pueda mostrar el número
    del DE sin pedir uno por fila: con 20 ventas por página, `obtener_documento`
    en el bucle son 20 consultas por carga.
    """
    if not venta_ids:
        return {}

    documentos = (
        DocumentoElectronico.query
        .filter(
            DocumentoElectronico.id_venta.in_(list(venta_ids)),
            db.or_(
                DocumentoElectronico.tipo_documento.is_(None),
                DocumentoElectronico.tipo_documento == TIPO_FACTURA,
            ),
        )
        .order_by(DocumentoElectronico.id.asc())
        .all()
    )
    # Ascendente y pisando: queda el de mayor id, que es el vigente — el mismo
    # criterio que `obtener_documento`, para que el listado y el detalle no
    # muestren documentos distintos de la misma venta.
    return {doc.id_venta: doc for doc in documentos}


def notas_credito(venta_id):
    """Notas de crédito de una venta, de la más nueva a la más vieja."""
    return (
        DocumentoElectronico.query
        .filter_by(id_venta=venta_id, tipo_documento=TIPO_NOTA_CREDITO)
        .order_by(DocumentoElectronico.id.desc())
        .all()
    )


def nota_credito_de_devolucion(devolucion):
    """La NC más reciente de esa devolución, o None."""
    return (
        DocumentoElectronico.query
        .filter_by(
            id_devolucion=devolucion.id_devolucion, tipo_documento=TIPO_NOTA_CREDITO,
        )
        .order_by(DocumentoElectronico.id.desc())
        .first()
    )


def nota_credito_de_correccion(venta_id):
    """La NC de anulación de esa venta (la que no tiene devolución detrás)."""
    return (
        DocumentoElectronico.query
        .filter(
            DocumentoElectronico.id_venta == venta_id,
            DocumentoElectronico.tipo_documento == TIPO_NOTA_CREDITO,
            DocumentoElectronico.id_devolucion.is_(None),
        )
        .order_by(DocumentoElectronico.id.desc())
        .first()
    )
