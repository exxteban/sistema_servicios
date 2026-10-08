"""Reenvío de un DE firmado que no llegó a SIFEN (motor propio).

Dos reglas: entre 72h y 720h se envía igual (SIFEN aprueba con observación
1005), y antes de reenviar algo cuyo envío falló se consulta el CDC y sólo se
reenvía si SIFEN dice que no lo tiene.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.models import Venta  # noqa: F401  (registra el mapper que usa DocumentoElectronico)
from facturacion_electronica import (
    AMBIENTE_TEST,
    ESTADO_APROBADO,
    ESTADO_ENVIADO,
    ESTADO_ERROR,
    ESTADO_RECHAZADO,
    MODO_ENVIO_SINCRONO,
)
from facturacion_electronica.services.retransmision import (
    AUSENTE,
    CONFIRMADO,
    INCONCLUSO,
    evaluar_plazo,
    evidencia_cdc,
    verificar_antes_de_reenviar,
)

ENVIO = 'facturacion_electronica.services.envio_service'
RETRANSMISION = 'facturacion_electronica.services.retransmision'

# Forma real de siConsDE: el protocolo viene dentro de xContenDE, como texto.
CDC_ENCONTRADO = {
    'ns2:rEnviConsDeResponse': {
        'ns2:dCodRes': '0422',
        'ns2:dMsgRes': 'CDC encontrado',
        'ns2:xContenDE': '<rContDe><rDE>...</rDE><dProtAut>48151623</dProtAut></rContDe>',
    },
}
CDC_AUSENTE = {
    'ns2:rEnviConsDeResponse': {
        'ns2:dCodRes': '0420',
        'ns2:dMsgRes': 'Documento No Existe en SIFEN o ha sido Rechazado',
    },
}


def _documento(estado=ESTADO_ERROR):
    return SimpleNamespace(
        id=7, cdc='0' * 44, estado=estado, respuesta_codigo=None, respuesta_mensaje=None,
        respuesta_raw=None, protocolo_autorizacion=None, fecha_envio=None,
    )


# --- plazo -----------------------------------------------------------------

def test_dentro_de_72h_no_hay_error_ni_aviso():
    ahora = datetime(2026, 10, 1, 12, 0)
    assert evaluar_plazo(ahora - timedelta(hours=10), ahora) == (None, None)


def test_entre_72_y_720h_se_envia_con_aviso_de_extemporaneo():
    ahora = datetime(2026, 10, 1, 12, 0)
    error, aviso = evaluar_plazo(ahora - timedelta(hours=100), ahora)
    assert error is None
    assert '1005' in aviso


def test_pasadas_720h_es_definitivo():
    ahora = datetime(2026, 10, 1, 12, 0)
    error, aviso = evaluar_plazo(ahora - timedelta(hours=721), ahora)
    assert '1150' in error
    assert aviso is None


# --- evidencia de siConsDE -------------------------------------------------

def test_cdc_encontrado_con_protocolo_en_xcontende_es_confirmado():
    assert evidencia_cdc(CDC_ENCONTRADO) == (CONFIRMADO, '0422', '48151623')


def test_cdc_encontrado_sin_protocolo_es_inconcluso():
    sin_protocolo = {'rEnviConsDeResponse': {'dCodRes': '0422', 'xContenDE': '<rDE/>'}}
    assert evidencia_cdc(sin_protocolo)[0] == INCONCLUSO


def test_0420_es_ausente():
    assert evidencia_cdc(CDC_AUSENTE)[0] == AUSENTE


def test_0420_con_protocolo_se_contradice_y_es_inconcluso():
    contradictorio = {'r': {'dCodRes': '0420', 'dProtAut': '123'}}
    assert evidencia_cdc(contradictorio)[0] == INCONCLUSO


def test_codigo_desconocido_es_inconcluso():
    assert evidencia_cdc({'r': {'dCodRes': '0999'}})[0] == INCONCLUSO


# --- verificar antes de reenviar -------------------------------------------

def test_si_sifen_no_lo_tiene_se_reenvia():
    documento = _documento()
    seguir, error = verificar_antes_de_reenviar(documento, lambda _cdc: (CDC_AUSENTE, None))
    assert seguir is True and error is None
    assert documento.estado == ESTADO_ERROR


def test_si_el_envio_anterior_llego_se_adopta_sin_reenviar():
    documento = _documento()
    with patch(f'{RETRANSMISION}.db'):
        seguir, error = verificar_antes_de_reenviar(documento, lambda _cdc: (CDC_ENCONTRADO, None))
    assert seguir is False and error is None
    assert documento.estado == ESTADO_APROBADO
    assert documento.protocolo_autorizacion == '48151623'


def test_respuesta_dudosa_no_reenvia_ni_aprueba():
    documento = _documento()
    seguir, error = verificar_antes_de_reenviar(
        documento, lambda _cdc: ({'r': {'dCodRes': '0422'}}, None),
    )
    assert seguir is False and 'a ciegas' in error
    assert documento.estado == ESTADO_ERROR


def test_consulta_caida_no_reenvia():
    documento = _documento()
    seguir, error = verificar_antes_de_reenviar(documento, lambda _cdc: (None, 'timeout'))
    assert seguir is False and 'timeout' in error


# --- integrado en enviar_documento ------------------------------------------

def _doc_para_enviar(estado, horas):
    from facturacion_electronica.models import DocumentoElectronico

    documento = DocumentoElectronico(
        id_venta=1, estado=estado, xml_firmado='<f/>', xml_qr='<q/>', cdc='0' * 44,
    )
    documento.id = 9
    return documento, datetime.utcnow() - timedelta(hours=horas)


def _enviar(documento, emitido_el, consulta=None, envio=None):
    from facturacion_electronica.services.emision_service import enviar_documento

    config = SimpleNamespace(cert_path='/c.p12', cert_password='', ambiente=AMBIENTE_TEST)
    with patch(f'{ENVIO}.obtener_configuracion', return_value=config), \
            patch(f'{ENVIO}.fecha_emision', return_value=emitido_el), \
            patch(f'{ENVIO}.error_venta_no_facturable', return_value=None), \
            patch(f'{ENVIO}.descifrar', return_value=''), \
            patch(f'{ENVIO}.modo_envio_efectivo', return_value=MODO_ENVIO_SINCRONO), \
            patch(f'{ENVIO}.consultar_de', return_value=consulta) as mock_consulta, \
            patch(f'{ENVIO}.enviar_de', return_value=envio) as mock_envio, \
            patch(f'{ENVIO}.db'), patch(f'{RETRANSMISION}.db'):
        _doc, error = enviar_documento(documento)
    return error, mock_consulta, mock_envio


APROBADO_EXTEMPORANEO = {
    'rRetEnviDe': {'rProtDe': {
        'dEstRes': 'Aprobado con observación', 'dProtAut': '777',
        'gResProc': {'dCodRes': '1005', 'dMsgRes': 'Transmisión extemporánea'},
    }},
}


def test_a_las_100h_un_firmado_se_envia_y_queda_aprobado_con_aviso():
    documento, emitido_el = _doc_para_enviar('firmado', 100)
    error, mock_consulta, mock_envio = _enviar(
        documento, emitido_el, envio=(APROBADO_EXTEMPORANEO, None),
    )
    assert error is None
    mock_consulta.assert_not_called()  # nunca falló: no hay nada que verificar
    mock_envio.assert_called_once()
    assert documento.estado == ESTADO_APROBADO
    assert 'extemporáneo' in documento.respuesta_mensaje


def test_a_las_721h_no_se_envia():
    documento, emitido_el = _doc_para_enviar('firmado', 721)
    error, _mock_consulta, mock_envio = _enviar(documento, emitido_el)
    assert '1150' in error
    mock_envio.assert_not_called()
    assert documento.estado == ESTADO_ERROR


def test_un_envio_fallido_que_si_llego_no_se_reenvia():
    documento, emitido_el = _doc_para_enviar(ESTADO_ERROR, 5)
    error, mock_consulta, mock_envio = _enviar(
        documento, emitido_el, consulta=(CDC_ENCONTRADO, None),
    )
    assert error is None
    mock_consulta.assert_called_once()
    mock_envio.assert_not_called()
    assert documento.estado == ESTADO_APROBADO


def test_un_envio_fallido_que_no_llego_se_reenvia():
    documento, emitido_el = _doc_para_enviar(ESTADO_ERROR, 5)
    aprobado = {'rProtDe': {'dEstRes': 'Aprobado', 'dProtAut': '1', 'dCodRes': '0260'}}
    error, _mock_consulta, mock_envio = _enviar(
        documento, emitido_el, consulta=(CDC_AUSENTE, None), envio=(aprobado, None),
    )
    assert error is None
    mock_envio.assert_called_once()
    assert documento.estado == ESTADO_APROBADO


def test_consultar_estado_reconoce_0422_como_aprobado():
    """Antes la consulta buscaba `dEstRes`, que siConsDE no trae: nunca aprobaba."""
    from facturacion_electronica.services.emision_service import consultar_documento

    documento = _documento(estado=ESTADO_ENVIADO)
    config = SimpleNamespace(cert_path='/c.p12', cert_password='', ambiente=AMBIENTE_TEST)
    with patch(f'{ENVIO}.obtener_configuracion', return_value=config), \
            patch(f'{ENVIO}.descifrar', return_value=''), \
            patch(f'{ENVIO}.consultar_de', return_value=(CDC_ENCONTRADO, None)), \
            patch(f'{RETRANSMISION}.db'):
        _respuesta, error = consultar_documento(documento)
    assert error is None
    assert documento.estado == ESTADO_APROBADO
    assert documento.protocolo_autorizacion == '48151623'


def test_consultar_estado_dudoso_no_toca_el_documento():
    from facturacion_electronica.services.emision_service import consultar_documento

    documento = _documento(estado=ESTADO_ENVIADO)
    config = SimpleNamespace(cert_path='/c.p12', cert_password='', ambiente=AMBIENTE_TEST)
    with patch(f'{ENVIO}.obtener_configuracion', return_value=config), \
            patch(f'{ENVIO}.descifrar', return_value=''), \
            patch(f'{ENVIO}.consultar_de', return_value=({'r': {'dCodRes': '0999'}}, None)):
        consultar_documento(documento)
    assert documento.estado == ESTADO_ENVIADO
    assert documento.estado != ESTADO_RECHAZADO
