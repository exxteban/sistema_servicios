"""Genera y persiste el documento electrónico de una venta.

Esta fase arma el XML (vía el microservicio TIPS) y lo guarda con su CDC y
estado. NO firma ni envía: eso requiere el certificado y se agrega después.
El código de seguridad se genera una sola vez y se reutiliza, para que el CDC
del documento sea estable entre regeneraciones.
"""
import re
from datetime import datetime

from app import db
from facturacion_electronica import (
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    ESTADO_GENERADO,
    ESTADOS_NO_REGENERABLES,
)
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.config_service import obtener_configuracion
from facturacion_electronica.services.crypto import descifrar
from facturacion_electronica.services.data_builder import (
    construir_data_venta,
    generar_codigo_seguridad,
)
from facturacion_electronica.services.sifen_client import firmar_xml, generar_xml
from facturacion_electronica.services.tips_payload import construir_params_emisor


_CDC_RE = re.compile(r'<DE\s+Id="(\d+)"')


def extraer_cdc(xml):
    if not xml:
        return None
    match = _CDC_RE.search(xml)
    return match.group(1) if match else None


def obtener_documento(venta_id):
    return DocumentoElectronico.query.filter_by(id_venta=venta_id).first()


def generar_documento(venta):
    """Arma el XML de la venta y lo guarda. Devuelve (documento, error)."""
    doc = obtener_documento(venta.id_venta)
    if doc is None:
        doc = DocumentoElectronico(
            id_venta=venta.id_venta,
            codigo_seguridad=generar_codigo_seguridad(),
        )
        db.session.add(doc)
    elif doc.estado in ESTADOS_NO_REGENERABLES:
        return doc, f'El documento ya está {doc.estado}; no se puede regenerar.'

    config = obtener_configuracion()
    params = construir_params_emisor(config)
    data = construir_data_venta(venta, config, codigo_seguridad=doc.codigo_seguridad)

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


__all__ = ['generar_documento', 'firmar_documento', 'obtener_documento', 'extraer_cdc']
