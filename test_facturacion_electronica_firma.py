from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.emision_service import firmar_documento


def test_firmar_sin_documento():
    _doc, error = firmar_documento(None)
    assert error and 'XML' in error


def test_firmar_sin_xml_generado():
    doc = DocumentoElectronico(id_venta=1, estado='generado', xml=None)
    _doc, error = firmar_documento(doc)
    assert error and 'Generá el documento' in error
