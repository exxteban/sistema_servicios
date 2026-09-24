from types import SimpleNamespace

from app.models import Venta  # noqa: F401  (registra el mapper que usa DocumentoElectronico)
from facturacion_electronica import (
    AMBIENTE_PRODUCCION,
    AMBIENTE_TEST,
    ESTADO_APROBADO,
    ESTADO_ENVIADO,
    ESTADO_RECHAZADO,
)
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.emision_service import (
    _ambiente_setapi,
    _buscar_clave,
    _interpretar_respuesta,
    enviar_documento,
)


def test_ambiente_setapi_mapea_a_test_prod():
    assert _ambiente_setapi(SimpleNamespace(ambiente=AMBIENTE_TEST)) == 'test'
    assert _ambiente_setapi(SimpleNamespace(ambiente=AMBIENTE_PRODUCCION)) == 'prod'


def test_buscar_clave_anidada():
    obj = {'a': {'b': [{'c': None}, {'dProtAut': '12345'}]}}
    assert _buscar_clave(obj, {'dProtAut'}) == '12345'
    assert _buscar_clave(obj, {'noExiste'}) is None


def test_buscar_clave_ignora_vacios():
    obj = {'dCodRes': '', 'sub': {'dCodRes': '0260'}}
    assert _buscar_clave(obj, {'dCodRes'}) == '0260'


def test_interpretar_respuesta_aprobado():
    resp = {'rRetEnviDe': {'dCodRes': '0260', 'dMsgRes': 'ok', 'rProtDe': {'dEstRes': 'Aprobado', 'dProtAut': '999'}}}
    estado, codigo, mensaje, protocolo = _interpretar_respuesta(resp)
    assert estado == ESTADO_APROBADO
    assert codigo == '0260'
    assert mensaje == 'ok'
    assert protocolo == '999'


def test_interpretar_respuesta_rechazado():
    resp = {'rProtDe': {'dEstRes': 'Rechazado', 'dMsgRes': 'error de timbrado'}}
    estado, _codigo, mensaje, _protocolo = _interpretar_respuesta(resp)
    assert estado == ESTADO_RECHAZADO
    assert mensaje == 'error de timbrado'


def test_interpretar_respuesta_real_de_sifen_con_namespace():
    """La respuesta de verdad trae `ns2:` pegado a cada nombre.

    Copiada tal cual del primer envío real al ambiente de prueba. Con las
    claves comparadas enteras, el rechazo no se reconocía: el documento
    quedaba en 'enviado', sin código ni motivo, aunque SIFEN había contestado
    "Rechazado" y el texto estaba guardado en respuesta_raw.
    """
    resp = {
        'ns2:rRetEnviDe': {
            '$': {'xmlns:ns2': 'http://ekuatia.set.gov.py/sifen/xsd'},
            'ns2:rProtDe': {
                'ns2:Id': '01801781051001001000000422026092019218158228',
                'ns2:dFecProc': '2026-09-20T18:55:34-03:00',
                'ns2:dEstRes': 'Rechazado',
                'ns2:gResProc': {
                    'ns2:dCodRes': '0160',
                    'ns2:dMsgRes': 'XML malformado [El valor  del elemento: cTipReg es invalido]',
                },
            },
        },
    }
    estado, codigo, mensaje, _protocolo = _interpretar_respuesta(resp)
    assert estado == ESTADO_RECHAZADO
    assert codigo == '0160'
    assert 'cTipReg' in mensaje


def test_la_consulta_0420_destraba_el_documento():
    """Un DE que SIFEN no tiene queda regenerable.

    Caso real: el envío fue rechazado, el sistema no supo leer la respuesta y
    el documento se quedó en 'enviado'. Ese estado no se puede regenerar, así
    que la venta no se podía volver a facturar. La consulta devuelve 0420
    ("Documento No Existe en SIFEN o ha sido Rechazado"), que es definitiva:
    la recepción es síncrona, si SIFEN lo hubiera aceptado lo encontraría.
    """
    from unittest.mock import patch

    from facturacion_electronica.services.emision_service import consultar_documento

    respuesta = {
        'ns2:rEnviConsDeResponse': {
            'ns2:dFecProc': '2026-09-20T18:56:57-03:00',
            'ns2:dCodRes': '0420',
            'ns2:dMsgRes': 'Documento No Existe en SIFEN o ha sido Rechazado',
        },
    }
    documento = SimpleNamespace(
        id=5, cdc='0' * 44, estado=ESTADO_ENVIADO,
        respuesta_codigo=None, respuesta_mensaje=None, respuesta_raw=None,
        protocolo_autorizacion=None,
    )
    config = SimpleNamespace(cert_path='/fake/cert.p12', cert_password='x', ambiente=AMBIENTE_TEST)

    with patch('facturacion_electronica.services.emision_service.obtener_configuracion',
               return_value=config), \
         patch('facturacion_electronica.services.emision_service.consultar_de',
               return_value=(respuesta, None)), \
         patch('facturacion_electronica.services.emision_service.db'):
        _respuesta, error = consultar_documento(documento)

    assert error is None
    assert documento.estado == ESTADO_RECHAZADO
    assert documento.respuesta_codigo == '0420'


def test_interpretar_respuesta_sin_estado_cae_a_enviado():
    estado, _c, _m, _p = _interpretar_respuesta({'algo': 'raro'})
    assert estado == ESTADO_ENVIADO


def test_enviar_documento_exige_qr_antes_de_enviar():
    # El nodo gCamFuFD/dCarQR es obligatorio en el rDE; sin QR, SIFEN rechazaría
    # el envío, así que no debe intentarse aunque el XML ya esté firmado.
    doc = DocumentoElectronico(id_venta=1, estado='firmado', xml_firmado='<firmado/>', xml_qr=None)
    _doc, error = enviar_documento(doc)
    assert error and 'QR' in error
