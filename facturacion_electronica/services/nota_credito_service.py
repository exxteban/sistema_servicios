"""Generación de notas de crédito: la de una devolución y la que anula una
factura entera.

Comparte con la factura la firma, el QR, el envío y la consulta; se diferencia
sólo en cómo se arma su `data` y en que lleva su propio correlativo dentro del
mismo timbrado.
"""
from datetime import datetime
from types import SimpleNamespace

from app import db
from facturacion_electronica import (
    ESTADO_CANCELADO,
    ESTADO_ERROR,
    ESTADO_GENERADO,
    ESTADOS_NO_REGENERABLES,
    TIPO_NOTA_CREDITO,
)
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.config_service import obtener_configuracion
from facturacion_electronica.services.data_builder import (
    construir_data_nota_credito,
    generar_codigo_seguridad,
)
from facturacion_electronica.services.documento_consulta import (
    extraer_cdc,
    nota_credito_de_correccion,
    nota_credito_de_devolucion,
    obtener_documento,
)
from facturacion_electronica.services.generacion_service import (
    firmar_documento,
    generar_qr_documento,
)
from facturacion_electronica.services.guarda import (
    error_devolucion_no_acreditable,
    error_original_no_acreditable,
)
from facturacion_electronica.services.nota_credito import (
    lineas_de_devolucion,
    lineas_de_venta,
    motivo_valido,
)
from facturacion_electronica.services.numeracion_service import reservar_numero
from facturacion_electronica.services.receptor_facturado import cliente_facturado_propio
from facturacion_electronica.services.sifen_client import generar_xml
from facturacion_electronica.services.tips_payload import construir_params_emisor


def generar_nota_credito(devolucion, motivo=None):
    """Arma el XML de la NC de una devolución y lo guarda. Devuelve (doc, error).

    El correlativo, el código de seguridad y la fecha se reservan una sola vez
    y se conservan entre regeneraciones, igual que en la factura: el CDC tiene
    que ser estable, y un fallo al firmar no puede consumir otro número del
    rango de notas de crédito.
    """
    error_devolucion = error_devolucion_no_acreditable(devolucion)
    if error_devolucion:
        return None, error_devolucion

    original = obtener_documento(devolucion.id_venta)
    error_original = error_original_no_acreditable(original)
    if error_original:
        return None, error_original

    doc = nota_credito_de_devolucion(devolucion)
    if doc is not None and doc.estado in ESTADOS_NO_REGENERABLES:
        if doc.estado != ESTADO_CANCELADO:
            return doc, f'La nota de crédito ya figura como {doc.estado}; no se puede regenerar.'
        # La NC anterior fue dada de baja en SIFEN: la devolución vuelve a
        # quedar sin acreditar y corresponde emitir una nueva.
        doc = None

    codigo_motivo, descripcion_motivo = motivo_valido(motivo)
    if codigo_motivo is None and doc is not None:
        # Reintento sin motivo en el formulario: vale el que ya eligió la
        # persona la primera vez.
        codigo_motivo, descripcion_motivo = motivo_valido(doc.nc_motivo)
    if codigo_motivo is None:
        return doc, 'Elegí un motivo del catálogo de SIFEN para la nota de crédito.'

    lineas = lineas_de_devolucion(devolucion)
    if not lineas:
        return doc, 'La devolución no tiene ítems para acreditar.'

    if doc is None:
        doc = DocumentoElectronico(
            id_venta=devolucion.id_venta,
            tipo_documento=TIPO_NOTA_CREDITO,
            id_devolucion=devolucion.id_devolucion,
            codigo_seguridad=generar_codigo_seguridad(),
        )
        db.session.add(doc)
    return _completar_nota_credito(
        doc, original, codigo_motivo, descripcion_motivo, lineas, devolucion,
    )


def _completar_nota_credito(doc, original, codigo_motivo, descripcion_motivo,
                            lineas, origen):
    """Numeración, XML y persistencia de una NC ya identificada.

    Lo comparten la NC de una devolución y la que anula una factura mal
    emitida: sólo cambian de dónde salen las líneas y qué documento las
    respalda. `origen` es lo que aporta la descripción libre del DE (la
    devolución, o el texto que escribió quien anula).
    """
    doc.id_documento_asociado = original.id
    doc.nc_motivo = codigo_motivo
    doc.nc_motivo_desc = descripcion_motivo

    config = obtener_configuracion()
    establecimiento = (config.establecimiento or '001').strip() or '001'
    punto = (config.punto_expedicion or '001').strip() or '001'
    if not doc.numero:
        numero, error_num = reservar_numero(establecimiento, punto, TIPO_NOTA_CREDITO)
        if error_num:
            doc.estado = ESTADO_ERROR
            doc.respuesta_mensaje = error_num
            db.session.commit()
            return doc, error_num
        doc.numero = numero
        doc.establecimiento = establecimiento
        doc.punto = punto
    # La fecha del DE entra en el CDC: se fija en la primera generación para
    # que regenerar no cambie el CDC ni corra la ventana de envío.
    if not doc.fecha_generado:
        doc.fecha_generado = datetime.utcnow()

    params = construir_params_emisor(config)
    data = construir_data_nota_credito(
        origen, config, original, codigo_motivo,
        venta=original.venta, lineas=lineas,
        codigo_seguridad=doc.codigo_seguridad, numero=doc.numero,
        fecha=doc.fecha_generado,
        cliente=cliente_facturado_propio(original, original.venta.cliente),
    )

    xml, error = generar_xml(params, data)
    if error:
        doc.estado = ESTADO_ERROR
        doc.respuesta_mensaje = error
        db.session.commit()
        return doc, error

    doc.establecimiento = data['establecimiento']
    doc.punto = data['punto']
    doc.timbrado = config.timbrado_numero
    doc.ambiente = config.ambiente
    doc.cdc = extraer_cdc(xml)
    doc.xml = xml
    doc.xml_firmado = None
    doc.xml_qr = None
    doc.qr_url = None
    doc.respuesta_codigo = None
    doc.respuesta_mensaje = None
    doc.respuesta_raw = None
    doc.estado = ESTADO_GENERADO
    db.session.commit()
    return doc, None


def generar_nota_credito_correccion(venta, motivo=None, descripcion=None):
    """NC que anula una factura entera, sin devolución. Devuelve (doc, error).

    Es la salida cuando la factura está mal y ya pasaron las 48h en que SIFEN
    admite el evento de cancelación: acredita el total facturado y deja el
    saldo del cliente en cero ante SIFEN.

    **No mueve plata ni stock**, igual que la NC de una devolución: la NC
    respalda un movimiento, no lo hace. Quien quiera revertir el cobro anula la
    venta después, que es el camino que ya hace el contra-asiento de caja.
    """
    if venta is None:
        return None, 'La venta ya no existe.'

    original = obtener_documento(venta.id_venta)
    error_original = error_original_no_acreditable(original)
    if error_original:
        return None, error_original

    doc = nota_credito_de_correccion(venta.id_venta)
    if doc is not None and doc.estado in ESTADOS_NO_REGENERABLES:
        if doc.estado != ESTADO_CANCELADO:
            return doc, (
                f'La factura ya tiene una nota de crédito de anulación {doc.estado}; '
                'no se puede emitir otra.'
            )
        doc = None

    codigo_motivo, descripcion_motivo = motivo_valido(motivo)
    if codigo_motivo is None and doc is not None:
        codigo_motivo, descripcion_motivo = motivo_valido(doc.nc_motivo)
    if codigo_motivo is None:
        return doc, 'Elegí un motivo del catálogo de SIFEN para la nota de crédito.'

    lineas = lineas_de_venta(venta)
    if not lineas:
        return doc, 'La venta no tiene ítems para acreditar.'

    if doc is None:
        doc = DocumentoElectronico(
            id_venta=venta.id_venta,
            tipo_documento=TIPO_NOTA_CREDITO,
            codigo_seguridad=generar_codigo_seguridad(),
        )
        db.session.add(doc)

    origen = SimpleNamespace(motivo=(descripcion or '').strip() or None)
    return _completar_nota_credito(
        doc, original, codigo_motivo, descripcion_motivo, lineas, origen,
    )


def emitir_nota_credito_correccion(venta, motivo=None, descripcion=None):
    """Cadena completa de la NC de anulación: generar → firmar → QR."""
    doc, error = generar_nota_credito_correccion(venta, motivo, descripcion)
    if error:
        return doc, error
    doc, error = firmar_documento(doc)
    if error:
        return doc, error
    return generar_qr_documento(doc)


def emitir_nota_credito(devolucion, motivo=None):
    """Cadena completa de la NC: generar → firmar → QR. Devuelve (doc, error).

    No la envía a SIFEN: eso lo hace el job, igual que con la factura del POS.
    """
    doc, error = generar_nota_credito(devolucion, motivo)
    if error:
        return doc, error
    doc, error = firmar_documento(doc)
    if error:
        return doc, error
    return generar_qr_documento(doc)
