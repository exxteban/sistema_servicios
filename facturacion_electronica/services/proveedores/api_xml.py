"""Copia local del XML firmado de los DE que emite la API.

El que tiene que conservar los comprobantes es el emisor, no el proveedor: si
la API no responde, cierra o el cliente cambia de proveedor, sin copia propia
se queda sin el XML de sus facturas. Por eso, apenas un documento de la API
queda aprobado (o cancelado: el XML de lo que se anuló también se conserva),
se baja una vez y se guarda en `xml_firmado`, la misma columna donde el motor
propio guarda el suyo. Lo que devuelve la API es el `<rDE>` completo, con QR.

Sólo se copia lo que SIFEN ya aprobó: antes de eso, un `correct/` cambia el
XML y la copia quedaría distinta de la que tiene SIFEN.

Que un documento de la API tenga `xml_firmado` no lo confunde con uno del
motor propio: `pertenencia` mira primero `api_documento_id`.

Nada acá lanza ni frena la emisión: un fallo deja el documento sin copia y se
reintenta más tarde.
"""
from datetime import datetime, timedelta

from app import db
from facturacion_electronica import ESTADO_APROBADO, ESTADO_CANCELADO
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.proveedores import PROVEEDOR_API
from facturacion_electronica.services.proveedores.api_documento import descargar_xml

ESTADOS_CON_COPIA = (ESTADO_APROBADO, ESTADO_CANCELADO)

# `xml_firmado` es TEXT: en MySQL son 65.535 bytes y en modo estricto un valor
# más largo revienta el UPDATE (SQLite no lo aplica, la suite no lo ve). Un DE
# así de grande se sigue sirviendo desde la API, sólo que sin copia.
BYTES_MAXIMOS = 65000

# Un documento que falló (sin artefacto en la API, XML demasiado grande) no se
# vuelve a pedir en cada pasada del job. Es por proceso: al reiniciar, se
# reintenta, que es lo que se quiere.
ESPERA_TRAS_FALLO = timedelta(hours=6)
_fallidos = {}


def _necesita_copia(documento):
    return bool(
        documento is not None
        and documento.api_documento_id
        and documento.estado in ESTADOS_CON_COPIA
        and not documento.xml_firmado
    )


def guardar_copia(documento, xml):
    """Guarda `xml` como copia local si corresponde. Devuelve True si la guardó."""
    if not xml or not _necesita_copia(documento):
        return False
    if len(xml.encode('utf-8')) > BYTES_MAXIMOS:
        _fallidos[documento.id] = datetime.utcnow()
        return False
    documento.xml_firmado = xml
    db.session.commit()
    return True


def copiar_xml(config, documento):
    """Baja el XML de la API y lo guarda. Devuelve el error, o None."""
    if not _necesita_copia(documento):
        return None
    xml, error = descargar_xml(config, documento)
    if error:
        _fallidos[documento.id] = datetime.utcnow()
        return error
    guardar_copia(documento, xml)
    return None


def xml_del_documento(config, documento):
    """XML para entregar: la copia local primero; si no hay, el de la API
    (y de paso queda guardado). Devuelve (xml, error)."""
    if documento is not None and documento.xml_firmado:
        return documento.xml_firmado, None
    xml, error = descargar_xml(config, documento)
    if error:
        return None, error
    guardar_copia(documento, xml)
    return xml, None


def completar_copias(config, limite=10):
    """Copia el XML de los documentos aprobados que todavía no lo tienen.

    Cubre los recién aprobados y también los que se aprobaron antes de que
    existiera la copia. Si la API no responde, corta la pasada: el resto daría
    el mismo error. Devuelve cuántos copió.
    """
    if getattr(config, 'proveedor', None) != PROVEEDOR_API:
        return 0
    ahora = datetime.utcnow()
    for doc_id, cuando in list(_fallidos.items()):
        if ahora - cuando >= ESPERA_TRAS_FALLO:
            _fallidos.pop(doc_id, None)

    consulta = (
        DocumentoElectronico.query
        .filter(DocumentoElectronico.api_documento_id.isnot(None))
        .filter(DocumentoElectronico.estado.in_(ESTADOS_CON_COPIA))
        .filter(DocumentoElectronico.xml_firmado.is_(None))
    )
    if _fallidos:
        consulta = consulta.filter(DocumentoElectronico.id.notin_(list(_fallidos)))
    pendientes = consulta.order_by(DocumentoElectronico.id.desc()).limit(limite).all()

    copiados = 0
    for documento in pendientes:
        if copiar_xml(config, documento):
            break
        if documento.xml_firmado:
            copiados += 1
    return copiados


__all__ = [
    'BYTES_MAXIMOS', 'ESTADOS_CON_COPIA', 'completar_copias', 'copiar_xml',
    'guardar_copia', 'xml_del_documento',
]
