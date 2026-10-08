from facturacion_electronica import ESTADO_APROBADO
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.emision_service import (
    firmar_documento,
    generar_qr_documento,
)


def test_firmar_sin_documento():
    _doc, error = firmar_documento(None)
    assert error and 'XML' in error


def test_firmar_sin_xml_generado():
    doc = DocumentoElectronico(id_venta=1, estado='generado', xml=None)
    _doc, error = firmar_documento(doc)
    assert error and 'Generá el documento' in error


def test_regenerar_qr_de_un_documento_aprobado_no_pisa_el_que_valida():
    """El QR viajó en el XML que SIFEN aprobó. Recalcularlo con otro CSC dejaría
    un KuDE que no verifica en e-Kuatia, así que el botón tiene que frenar."""
    doc = DocumentoElectronico(
        id_venta=1, estado=ESTADO_APROBADO, xml_firmado='<rDE/>',
        qr_url='https://ekuatia.set.gov.py/consultas-test/qr?Id=1',
    )
    _doc, error = generar_qr_documento(doc)
    assert error and 'aprobado' in error
    assert doc.qr_url == 'https://ekuatia.set.gov.py/consultas-test/qr?Id=1'


def test_regenerar_qr_si_el_documento_aprobado_se_quedo_sin_el():
    """La guarda no puede bloquear el caso inverso: un aprobado sin QR no tiene
    nada que arruinar y ésta es la única forma de recuperarle el KuDE."""
    from unittest.mock import patch

    doc = DocumentoElectronico(
        id_venta=1, estado=ESTADO_APROBADO, xml_firmado='<rDE/>', qr_url=None,
    )
    # Si la guarda frenara, nunca se llegaría a leer la config. Se corta ahí
    # para no necesitar ni base ni el servicio Node.
    centinela = RuntimeError('pasó la guarda')
    with patch(
        'facturacion_electronica.services.generacion_service.obtener_configuracion',
        side_effect=centinela,
    ):
        try:
            generar_qr_documento(doc)
        except RuntimeError as exc:
            assert exc is centinela
        else:
            raise AssertionError('la guarda frenó un documento aprobado sin QR')
