"""Generación de la factura: arma el XML (vía el microservicio TIPS), lo firma
y le agrega el QR.

El código de seguridad y el número se generan una sola vez y se reutilizan,
para que el CDC del documento sea estable entre regeneraciones.
"""
from datetime import datetime

from app import db
from facturacion_electronica import (
    AMBIENTE_PRODUCCION,
    CSC_DEMO,
    CSC_DEMO_ID,
    ESTADO_CANCELADO,
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    ESTADO_GENERADO,
    ESTADO_INUTILIZADO,
    ESTADOS_NO_REGENERABLES,
)
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.config_service import obtener_configuracion
from facturacion_electronica.services.crypto import descifrar
from facturacion_electronica.services.data_builder import (
    construir_data_venta,
    generar_codigo_seguridad,
)
from facturacion_electronica.services.documento_consulta import extraer_cdc, obtener_documento
from facturacion_electronica.services.guarda import error_venta_no_facturable
from facturacion_electronica.services.numeracion_service import reservar_numero
from facturacion_electronica.services.qr import extraer_qr_url
from facturacion_electronica.services.sifen_client import firmar_xml, generar_qr, generar_xml
from facturacion_electronica.services.tips_payload import construir_params_emisor
from facturacion_electronica.services.validacion import validar_cliente, validar_monto_innominado


def generar_documento(venta):
    """Arma el XML de la venta y lo guarda. Devuelve (documento, error)."""
    from app.services.caja_transacciones import bloquear_caja_de_venta

    bloquear_caja_de_venta(venta)
    error_venta = error_venta_no_facturable(venta)
    if error_venta:
        doc = obtener_documento(venta.id_venta)
        if doc is not None and doc.estado not in ESTADOS_NO_REGENERABLES:
            doc.estado = ESTADO_ERROR
            doc.respuesta_mensaje = error_venta
            db.session.commit()
        return doc, error_venta
    doc = obtener_documento(venta.id_venta)
    if doc is not None and doc.estado in ESTADOS_NO_REGENERABLES:
        if doc.estado not in (ESTADO_CANCELADO, ESTADO_INUTILIZADO):
            return doc, f'El documento ya está {doc.estado}; no se puede regenerar.'
        # Re-facturación: el DE vigente se canceló en SIFEN (estaba aprobado) o
        # su número se inutilizó (nunca llegó a transmitirse). En los dos casos
        # el documento viejo no se toca —es historial fiscal, y su número ya no
        # se puede reusar— y la venta arranca uno nuevo con su propio número.
        doc = None
    if doc is None:
        doc = DocumentoElectronico(
            id_venta=venta.id_venta,
            codigo_seguridad=generar_codigo_seguridad(),
        )
        db.session.add(doc)

    # Datos del cliente que invalidarían la factura para el receptor (ej. RUC de
    # empresa sin DV). Se frena antes de reservar número: corregir la ficha del
    # cliente no consume correlativos y el reintento automático regenera el DE.
    error_cliente = validar_cliente(venta.cliente) or validar_monto_innominado(
        venta.cliente, venta.total,
    )
    if error_cliente:
        doc.estado = ESTADO_ERROR
        doc.respuesta_mensaje = error_cliente
        db.session.commit()
        return doc, error_cliente

    config = obtener_configuracion()

    establecimiento = (config.establecimiento or '001').strip() or '001'
    punto = (config.punto_expedicion or '001').strip() or '001'
    # El número se reserva una sola vez y se conserva entre regeneraciones, para
    # mantener la correlatividad y que el CDC sea estable (igual que el código de
    # seguridad). Un fallo posterior no consume un número nuevo en el reintento.
    if not doc.numero:
        numero, error_num = reservar_numero(establecimiento, punto)
        if error_num:
            doc.estado = ESTADO_ERROR
            db.session.commit()
            return doc, error_num
        doc.numero = numero
        doc.establecimiento = establecimiento
        doc.punto = punto

    params = construir_params_emisor(config)
    data = construir_data_venta(
        venta, config, codigo_seguridad=doc.codigo_seguridad, numero=doc.numero,
    )

    xml, error = generar_xml(params, data)
    if error:
        doc.estado = ESTADO_ERROR
        db.session.commit()
        return doc, error

    doc.tipo_documento = data['tipoDocumento']
    doc.establecimiento = data['establecimiento']
    doc.punto = data['punto']
    doc.numero = data['numero']
    doc.timbrado = config.timbrado_numero
    doc.ambiente = config.ambiente
    doc.cdc = extraer_cdc(xml)
    doc.xml = xml
    # Al regenerar se invalida cualquier firma/QR previo: corresponden al XML
    # anterior (otro CDC) y no deben reenviarse a SIFEN.
    doc.xml_firmado = None
    doc.xml_qr = None
    doc.qr_url = None
    # Limpia el resultado de un intento anterior (ej. el aviso de RUC sin DV):
    # ya no describe a este XML y confundiría en la UI.
    doc.respuesta_codigo = None
    doc.respuesta_mensaje = None
    doc.respuesta_raw = None
    doc.estado = ESTADO_GENERADO
    doc.fecha_generado = datetime.utcnow()
    db.session.commit()
    return doc, None


def firmar_documento(documento):
    """Firma el XML guardado del documento con el certificado de la config."""
    if documento is None or not documento.xml:
        return documento, 'No hay XML generado para firmar. Generá el documento primero.'
    if documento.estado in ESTADOS_NO_REGENERABLES:
        return documento, f'El documento ya está {documento.estado}.'

    config = obtener_configuracion()
    if not config.cert_path:
        return documento, 'Falta cargar el certificado digital (.p12) en la configuración.'

    firmado, error = firmar_xml(documento.xml, config.cert_path, descifrar(config.cert_password or ''))
    if error:
        return documento, error

    documento.xml_firmado = firmado
    documento.estado = ESTADO_FIRMADO
    db.session.commit()
    return documento, None


def generar_qr_documento(documento):
    """Agrega el QR (gCamFuFD/dCarQR) al XML firmado y persiste la URL.

    Usa el CSC de la config; si no está cargado, cae al CSC de maqueta para
    poder mostrar el KuDE en demo (el hash no es válido contra SIFEN).
    """
    if documento is None or not documento.xml_firmado:
        return documento, 'Primero firmá el documento; el QR se calcula sobre el XML firmado.'

    # El QR ya viajó dentro del XML que SIFEN aprobó. Recalcularlo con otro CSC
    # pisaría `qr_url` con un hash que no verifica contra e-Kuatia, y el KuDE
    # que se lleva el cliente dejaría de validar. Se permite sólo cuando falta:
    # ahí no hay nada que arruinar y es la única forma de recuperar el KuDE.
    if documento.estado in ESTADOS_NO_REGENERABLES and documento.qr_url:
        return documento, (
            f'El documento ya está {documento.estado} y tiene su QR. Regenerarlo con otro '
            'CSC dejaría un KuDE que no valida en e-Kuatia.'
        )

    config = obtener_configuracion()
    if config.ambiente == AMBIENTE_PRODUCCION and not (config.csc and config.csc_id):
        # El CSC de maqueta genera un QR que no verifica contra e-Kuatia; en
        # producción eso entregaría un KuDE fiscalmente inválido al cliente.
        return documento, 'Falta cargar el CSC real en la configuración para generar el QR en producción.'
    if config.ambiente == AMBIENTE_PRODUCCION and (config.csc or '').strip() == CSC_DEMO:
        # El CSC de pruebas de la DNIT es este mismo valor, así que "está
        # cargado" no alcanza: al pasar a producción hay que reemplazarlo.
        return documento, (
            'El CSC cargado es el de pruebas. Cargá el CSC real de la DNIT antes de '
            'emitir en producción, o el QR del KuDE no va a validar.'
        )
    id_csc = config.csc_id or CSC_DEMO_ID
    csc = config.csc or CSC_DEMO

    xml_con_qr, error = generar_qr(documento.xml_firmado, id_csc, csc, config.ambiente)
    if error:
        return documento, error

    documento.xml_qr = xml_con_qr
    documento.qr_url = extraer_qr_url(xml_con_qr)
    db.session.commit()
    return documento, None


def emitir_para_pos(venta):
    """Cadena completa para el POS: generar → firmar → QR. Devuelve (doc, error).

    Se llama DESPUÉS de que la venta ya está registrada; si algo falla, el error
    se devuelve para que el POS caiga al ticket normal sin romper la venta.
    """
    doc, error = generar_documento(venta)
    if error:
        return doc, error
    doc, error = firmar_documento(doc)
    if error:
        return doc, error
    return generar_qr_documento(doc)
