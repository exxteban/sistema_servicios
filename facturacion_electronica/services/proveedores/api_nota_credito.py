"""Piezas de la nota de crédito en modo API que no entran en `api.py`.

Dos cosas, y las dos salieron de la NC de anulación de la venta #123
(Janelipy, 2026-09-27), la primera que se transmitió por la API:

- **El receptor sale de la factura, no de la ficha.** Ver `receptor_facturado`.
  Acá se baja el XML de la factura de la API para leerlo.
- **Una NC rechazada se vuelve a dar de alta.** `correct/` es sólo para
  facturas (`409 document_not_correctable`). Pero un `REJECTED` libera del
  lado de la API el número fiscal y el `external_ref`, así que la salida es un
  alta nueva **con el mismo número**: no queda hueco en el correlativo y no
  hace falta inutilizar nada. Antes, "Anular con NC" sobre una NC rechazada
  sólo la volvía a consultar y avisaba "emitida" sin mandar nada.
"""
from datetime import datetime

from facturacion_electronica import ESTADO_GENERADO, ESTADO_RECHAZADO
from facturacion_electronica.services.data_builder import generar_codigo_seguridad
from facturacion_electronica.services.emision_service import HORAS_LIMITE_CANCELACION
from facturacion_electronica.services.guarda import (
    error_estado_original,
    error_receptor_original,
)
from facturacion_electronica.services.proveedores.api_documento import (
    clave_idempotencia,
    descargar_xml,
)
from facturacion_electronica.services.proveedores.api_payload import construir_nota_credito_api
from facturacion_electronica.services.receptor_facturado import (
    leer_receptor,
    receptor_api,
    redondeo_declarado,
)

NC_NO_HABILITADA = (
    'Las notas de crédito por la API de facturación electrónica todavía no están '
    'habilitadas: el proveedor aún no transmitió ninguna a SIFEN. Mientras tanto, si la '
    f'factura tiene menos de {HORAS_LIMITE_CANCELACION}h se la puede anular en SIFEN; si ya '
    'pasaron, hay que esperar a que se habiliten.'
)


def _xml_de_factura(config, original):
    """XML de la factura en la API. (xml, error) con el error ya redactado."""
    xml, error = descargar_xml(config, original)
    if error:
        return None, f'No se pudo leer el receptor de la factura que se acredita: {error}'
    return xml, None


def verificar_original(config, original):
    """`error_original_no_acreditable` con el receptor del XML de la API. (xml, error).

    Va antes de reservar el número de la NC: decidir con la ficha del cliente
    dejaba pasar la NC de una factura innominada si después se cargó la
    cédula, y SIFEN la rechazaba con el correlativo ya consumido. El XML que
    se baja acá se reusa al armar el cuerpo, así no se pide dos veces.
    """
    error = error_estado_original(original)
    if error:
        return None, error
    xml, error = _xml_de_factura(config, original)
    if error:
        return None, error
    error = error_receptor_original(original, xml)
    if error:
        return None, error
    return xml, None


def armar_cuerpo_nc(config, documento, original, venta, lineas, timbrado_id, xml=None):
    """Cuerpo del alta de la NC con el receptor de la factura. (cuerpo, error).

    Sin el XML de la factura no se emite: caer a la ficha del cliente es
    justamente el error que esto corrige, y un fallo al bajarlo es pasajero
    (el próximo intento lo vuelve a pedir). `xml` es el que ya bajó
    `verificar_original`; sin él se baja acá.
    """
    if xml is None:
        xml, error = _xml_de_factura(config, original)
        if error:
            return None, error
    campos = leer_receptor(xml)
    if not campos:
        return None, ('El XML de la factura no trae el receptor (gDatRec): no se puede '
                      'armar una nota de crédito para el mismo comprador.')
    cuerpo = construir_nota_credito_api(
        documento, original, venta, lineas, timbrado_id, receptor=receptor_api(campos),
        redondear=redondeo_declarado(xml) > 0,
    )
    return cuerpo, None


def reabrir_nc_rechazada(documento):
    """Deja una NC rechazada lista para un alta nueva. True si la reabrió.

    Conserva el número (la API lo liberó con el rechazo) y el motivo. Todo lo
    que era del alta anterior se borra: su id remoto, CDC, QR y la respuesta de
    SIFEN. La clave de idempotencia se estrena —con la vieja la API devolvería
    el documento rechazado— y la fecha también: la NC se emite ahora.
    """
    if documento.estado != ESTADO_RECHAZADO or not documento.api_documento_id:
        return False
    documento.api_documento_id = None
    documento.api_lote_id = None
    documento.cdc = None
    documento.qr_url = None
    documento.protocolo_autorizacion = None
    documento.respuesta_codigo = None
    documento.respuesta_mensaje = None
    documento.respuesta_raw = None
    documento.fecha_envio = None
    documento.fecha_generado = datetime.utcnow()
    documento.estado = ESTADO_GENERADO
    # La clave sale del código de seguridad (ver `clave_idempotencia`): uno
    # nuevo es una clave nueva con el mismo formato de siempre.
    documento.codigo_seguridad = generar_codigo_seguridad()
    documento.api_idempotency_key = None
    clave_idempotencia(documento)
    return True


__all__ = ['NC_NO_HABILITADA', 'armar_cuerpo_nc', 'reabrir_nc_rechazada', 'verificar_original']
