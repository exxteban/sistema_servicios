"""Envío por lote del motor propio (siRecepLoteDE + siConsLoteDE).

`LOTE_RECIBIDO` y `LOTE_EN_PROCESO` son copias de las respuestas reales del
primer lote a SIFEN TEST (2026-10-03, venta 001-001-0000204, lote
81111631107047170). El lote **concluido** (`0362`) todavía está armado según
el Manual Técnico v150: cuando llegue el primero, reemplazar `_lote_concluido`
por lo que contestó SIFEN (ver DIAGNOSTICO_SIFEN.md y la lección de las
fixtures sin `ns2:`).
"""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import create_app, db
from facturacion_electronica import (
    AMBIENTE_PRODUCCION,
    AMBIENTE_TEST,
    ESTADO_APROBADO,
    ESTADO_ENVIADO,
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    ESTADO_RECHAZADO,
    MODO_ENVIO_LOTE,
    MODO_ENVIO_SINCRONO,
)
from facturacion_electronica.services.envio_lote import (
    es_de_lote_propio,
    lote_recien_enviado,
    modo_envio,
    modo_envio_efectivo,
)
from facturacion_electronica.services.envio_service import consultar_documento, enviar_documento
from test_facturacion_electronica_proveedor_base import BaseProveedorApi

CDC = '01801781051001001000020322026100310633413286'
CONFIG = SimpleNamespace(cert_path='/fake/cert.p12', cert_password='', ambiente=AMBIENTE_TEST)

LOTE_RECIBIDO = {
    'ns2:rResEnviLoteDe': {
        '$': {'xmlns:ns2': 'http://ekuatia.set.gov.py/sifen/xsd'},
        'ns2:dFecProc': '2026-10-03T11:40:24-03:00',
        'ns2:dCodRes': '0300',
        'ns2:dMsgRes': 'Lote recibido con éxito',
        'ns2:dProtConsLote': '81111631107047170',
        'ns2:dTpoProces': '0',
    },
    'id': 66,
}
LOTE_NO_ENCOLADO = {
    'ns2:rResEnviLoteDe': {'ns2:dCodRes': '0301', 'ns2:dMsgRes': 'Lote no encolado para procesamiento',
                           'ns2:dProtConsLote': '0'},
}
LOTE_EN_PROCESO = {
    'ns2:rResEnviConsLoteDe': {
        '$': {'xmlns:ns2': 'http://ekuatia.set.gov.py/sifen/xsd'},
        'ns2:dFecProc': '2026-10-03T11:40:48-03:00',
        'ns2:dCodResLot': '0361',
        'ns2:dMsgResLot': 'Lote {81111631107047170} en procesamiento',
    },
    'id': 66,
}


def _lote_concluido(estado, cod='0260', msg='Autorización del DE satisfactoria', protocolo='50094099'):
    return {
        'ns2:rResEnviConsLoteDe': {
            'ns2:dCodResLot': '0362',
            'ns2:dMsgResLot': 'Procesamiento de lote concluido',
            'ns2:gResProcLote': {
                'ns2:id': CDC,
                'ns2:dEstRes': estado,
                'ns2:dProtAut': protocolo,
                'ns2:gResProc': {'ns2:dCodRes': cod, 'ns2:dMsgRes': msg},
            },
        },
    }


def _documento(**extra):
    datos = dict(
        id=7, cdc=CDC, estado=ESTADO_FIRMADO, venta=None,
        xml_firmado='<?xml version="1.0"?>\n<rDE/>', xml_qr='<?xml version="1.0"?>\n<rDE/>',
        respuesta_codigo=None, respuesta_mensaje=None, respuesta_raw=None,
        protocolo_autorizacion=None, fecha_envio=None,
        api_lote_id=None, api_documento_id=None,
    )
    datos.update(extra)
    return SimpleNamespace(**datos)


def _servicio(modo=MODO_ENVIO_LOTE, **parches):
    """Parchea la config, el modo y el commit; `parches` reemplaza llamadas a SIFEN."""
    base = {
        'facturacion_electronica.services.envio_service.obtener_configuracion': MagicMock(return_value=CONFIG),
        'facturacion_electronica.services.envio_service.modo_envio_efectivo': MagicMock(return_value=modo),
        'facturacion_electronica.services.envio_service.db': MagicMock(),
        'facturacion_electronica.services.envio_lote.db': MagicMock(),
        'facturacion_electronica.services.retransmision.db': MagicMock(),
    }
    base.update({f'facturacion_electronica.services.envio_service.{k}': v for k, v in parches.items()})
    return [patch(objetivo, nuevo) for objetivo, nuevo in base.items()]


class _ConParches(unittest.TestCase):
    def _con(self, parches):
        for p in parches:
            p.start()
            self.addCleanup(p.stop)


class TestEnvioEnLote(_ConParches):
    def test_lote_recibido_queda_enviado_con_su_numero_y_sin_protocolo(self):
        enviar = MagicMock(return_value=(LOTE_RECIBIDO, None))
        sincrono = MagicMock()
        self._con(_servicio(enviar_lote=enviar, enviar_de=sincrono))
        doc = _documento()

        _doc, error = enviar_documento(doc, forzar_fecha=True)

        self.assertIsNone(error)
        sincrono.assert_not_called()
        self.assertEqual(enviar.call_args[0][0], [doc.xml_qr])
        self.assertEqual(doc.estado, ESTADO_ENVIADO)
        self.assertEqual(doc.api_lote_id, '81111631107047170')
        self.assertEqual(doc.respuesta_codigo, '0300')
        # El número de lote no es un protocolo de autorización.
        self.assertIsNone(doc.protocolo_autorizacion)
        self.assertIn('81111631107047170', doc.respuesta_mensaje)

    def test_lote_no_encolado_es_error_y_se_puede_reenviar(self):
        self._con(_servicio(enviar_lote=MagicMock(return_value=(LOTE_NO_ENCOLADO, None))))
        doc = _documento()

        _doc, error = enviar_documento(doc, forzar_fecha=True)

        self.assertIn('0301', error)
        self.assertEqual(doc.estado, ESTADO_ERROR)
        self.assertIsNone(doc.api_lote_id)

    def test_en_modo_sincrono_no_toca_el_lote_y_borra_un_numero_viejo(self):
        enviar = MagicMock()
        respuesta = {'ns2:rRetEnviDe': {'ns2:rProtDe': {
            'ns2:dEstRes': 'Aprobado', 'ns2:dProtAut': '111',
            'ns2:gResProc': {'ns2:dCodRes': '0260', 'ns2:dMsgRes': 'ok'}}}}
        self._con(_servicio(modo=MODO_ENVIO_SINCRONO, enviar_lote=enviar,
                            enviar_de=MagicMock(return_value=(respuesta, None))))
        doc = _documento(api_lote_id='999')

        enviar_documento(doc, forzar_fecha=True)

        enviar.assert_not_called()
        self.assertEqual(doc.estado, ESTADO_APROBADO)
        self.assertIsNone(doc.api_lote_id)


class TestConsultaDeLote(_ConParches):
    def _consultar(self, respuesta_lote, consultar_de=None):
        por_cdc = consultar_de or MagicMock()
        self._con(_servicio(consultar_lote=MagicMock(return_value=(respuesta_lote, None)),
                            consultar_de=por_cdc))
        doc = _documento(estado=ESTADO_ENVIADO, api_lote_id='81111631107047170', respuesta_codigo='0300')
        _respuesta, error = consultar_documento(doc)
        return doc, error, por_cdc

    def test_en_proceso_sigue_enviado_y_no_pregunta_por_cdc(self):
        doc, error, por_cdc = self._consultar(LOTE_EN_PROCESO)

        self.assertIsNone(error)
        # Por CDC daría 0420 y lo marcaría rechazado mientras SIFEN lo procesa.
        por_cdc.assert_not_called()
        self.assertEqual(doc.estado, ESTADO_ENVIADO)
        self.assertEqual(doc.respuesta_codigo, '0361')
        self.assertIn('81111631107047170', doc.respuesta_mensaje)

    def test_concluido_aprobado_toma_el_protocolo(self):
        doc, error, _ = self._consultar(_lote_concluido('Aprobado'))

        self.assertIsNone(error)
        self.assertEqual(doc.estado, ESTADO_APROBADO)
        self.assertEqual(doc.protocolo_autorizacion, '50094099')
        self.assertEqual(doc.respuesta_codigo, '0260')

    def test_aprobado_con_observacion_tambien_es_aprobado(self):
        doc, _error, _ = self._consultar(
            _lote_concluido('Aprobado con observación', cod='1005', msg='Transmisión extemporánea'))

        self.assertEqual(doc.estado, ESTADO_APROBADO)
        self.assertEqual(doc.respuesta_codigo, '1005')

    def test_concluido_rechazado_deja_codigo_y_motivo(self):
        doc, _error, _ = self._consultar(
            _lote_concluido('Rechazado', cod='2501', msg='Valor del hash del QR inválido', protocolo='0'))

        self.assertEqual(doc.estado, ESTADO_RECHAZADO)
        self.assertEqual(doc.respuesta_codigo, '2501')
        self.assertIn('QR', doc.respuesta_mensaje)
        self.assertIsNone(doc.protocolo_autorizacion)

    def test_un_resultado_de_otro_cdc_no_aprueba_el_documento(self):
        respuesta = _lote_concluido('Aprobado')
        respuesta['ns2:rResEnviConsLoteDe']['ns2:gResProcLote']['ns2:id'] = '0' * 44
        doc, error, _ = self._consultar(respuesta)

        self.assertIsNotNone(error)
        self.assertEqual(doc.estado, ESTADO_ENVIADO)
        self.assertIsNone(doc.protocolo_autorizacion)

    def test_lote_extemporaneo_cae_a_la_consulta_por_cdc(self):
        extemporaneo = {'ns2:rResEnviConsLoteDe': {'ns2:dCodResLot': '0364',
                                                   'ns2:dMsgResLot': 'Consulta extemporánea de Lote'}}
        encontrado = {'ns2:rEnviConsDeResponse': {
            'ns2:dCodRes': '0422', 'ns2:dMsgRes': 'CDC encontrado',
            'ns2:xContenDE': '&lt;dProtAut&gt;50094100&lt;/dProtAut&gt;'}}
        doc, error, por_cdc = self._consultar(
            extemporaneo, consultar_de=MagicMock(return_value=(encontrado, None)))

        self.assertIsNone(error)
        por_cdc.assert_called_once()
        self.assertEqual(doc.estado, ESTADO_APROBADO)
        self.assertEqual(doc.protocolo_autorizacion, '50094100')


CDC_APROBADO = {'ns2:rEnviConsDeResponse': {
    'ns2:dCodRes': '0422', 'ns2:dMsgRes': 'CDC encontrado',
    'ns2:xContenDE': '&lt;dProtAut&gt;50094200&lt;/dProtAut&gt;'}}
CDC_NO_EXISTE = {'ns2:rEnviConsDeResponse': {
    'ns2:dCodRes': '0420', 'ns2:dMsgRes': 'Documento No Existe en SIFEN o ha sido Rechazado'}}


class TestRespaldoPorCdc(_ConParches):
    """Lote trabado en 0361: pasada una hora se pregunta además por CDC."""

    def _consultar_hace(self, minutos, respuesta_cdc):
        por_cdc = MagicMock(return_value=(respuesta_cdc, None))
        self._con(_servicio(consultar_lote=MagicMock(return_value=(LOTE_EN_PROCESO, None)),
                            consultar_de=por_cdc))
        doc = _documento(estado=ESTADO_ENVIADO, api_lote_id='81111631107047170',
                         fecha_envio=datetime.utcnow() - timedelta(minutes=minutos))
        _respuesta, error = consultar_documento(doc)
        self.assertIsNone(error)
        return doc, por_cdc

    def test_pasada_una_hora_si_sifen_lo_tiene_aprobado_se_adopta(self):
        doc, por_cdc = self._consultar_hace(90, CDC_APROBADO)

        por_cdc.assert_called_once()
        self.assertEqual(doc.estado, ESTADO_APROBADO)
        self.assertEqual(doc.protocolo_autorizacion, '50094200')
        self.assertIn('CDC', doc.respuesta_mensaje)

    def test_un_0420_no_lo_marca_rechazado(self):
        # Con el lote en proceso SIFEN siempre dice "no existe" por CDC.
        doc, por_cdc = self._consultar_hace(90, CDC_NO_EXISTE)

        por_cdc.assert_called_once()
        self.assertEqual(doc.estado, ESTADO_ENVIADO)
        self.assertEqual(doc.respuesta_codigo, '0361')

    def test_antes_de_la_hora_no_pregunta_por_cdc(self):
        doc, por_cdc = self._consultar_hace(30, CDC_APROBADO)

        por_cdc.assert_not_called()
        self.assertEqual(doc.estado, ESTADO_ENVIADO)


class TestEsperaDeDiezMinutos(unittest.TestCase):
    def test_lote_recien_enviado(self):
        ahora = datetime(2026, 10, 3, 15, 0)
        doc = _documento(api_lote_id='1', fecha_envio=ahora - timedelta(minutes=5))
        self.assertTrue(lote_recien_enviado(doc, ahora))
        doc.fecha_envio = ahora - timedelta(minutes=15)
        self.assertFalse(lote_recien_enviado(doc, ahora))
        # Un envío síncrono no espera: no tiene lote.
        self.assertFalse(lote_recien_enviado(_documento(fecha_envio=ahora), ahora))

    def test_el_job_no_consulta_un_lote_de_hace_cinco_minutos(self):
        from facturacion_electronica.services.proveedores.propio import ProveedorPropio

        proveedor = ProveedorPropio()
        doc = _documento(estado=ESTADO_ENVIADO, api_lote_id='1', xml='<rDE/>',
                         fecha_envio=datetime.utcnow() - timedelta(minutes=5))
        with patch.object(ProveedorPropio, 'consultar') as consultar:
            self.assertIsNone(proveedor.avanzar(doc))
        consultar.assert_not_called()

        doc.fecha_envio = datetime.utcnow() - timedelta(minutes=15)
        with patch.object(ProveedorPropio, 'consultar', return_value=(None, None)) as consultar:
            proveedor.avanzar(doc)
        consultar.assert_called_once()


class TestDocumentoDeLaApi(unittest.TestCase):
    def test_un_documento_de_la_api_no_se_consulta_como_lote_propio(self):
        # `api_lote_id` lo llenaba la API antes de que lotee su pipeline.
        self.assertFalse(es_de_lote_propio(SimpleNamespace(api_lote_id='abc', api_documento_id='uuid')))
        self.assertTrue(es_de_lote_propio(SimpleNamespace(api_lote_id='123', api_documento_id=None)))


class TestModoEnvioConfigurado(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_por_defecto_es_sincrono_y_se_guarda_desde_la_configuracion(self):
        from facturacion_electronica.services.config_service import guardar_configuracion

        self.assertEqual(modo_envio(), MODO_ENVIO_SINCRONO)
        guardar_configuracion({'proveedor': 'propio', 'ambiente': 'test', 'modo_envio': 'lote'})
        self.assertEqual(modo_envio(), MODO_ENVIO_LOTE)
        # En producción manda lote aunque se haya elegido síncrono: SIFEN no
        # acepta siRecepDE fuera del ambiente de prueba.
        guardar_configuracion({'proveedor': 'propio', 'ambiente': 'test', 'modo_envio': 'sincrono'})
        self.assertEqual(modo_envio_efectivo(SimpleNamespace(ambiente=AMBIENTE_TEST)), MODO_ENVIO_SINCRONO)
        self.assertEqual(modo_envio_efectivo(SimpleNamespace(ambiente=AMBIENTE_PRODUCCION)), MODO_ENVIO_LOTE)
        # Un valor desconocido no deja el sistema en un modo inventado.
        guardar_configuracion({'proveedor': 'propio', 'ambiente': 'test', 'modo_envio': 'otro'})
        self.assertEqual(modo_envio(), MODO_ENVIO_SINCRONO)


class TestPantallaModoEnvio(BaseProveedorApi):
    def test_la_pantalla_ofrece_el_modo_y_marca_el_guardado(self):
        from app.models import Usuario

        admin = Usuario.query.filter_by(username='admin').first()
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin.id_usuario)
            sess['_fresh'] = True

        html = client.get('/facturacion-electronica/configuracion').get_data(as_text=True)
        self.assertIn('name="modo_envio"', html)
        self.assertIn('<option value="sincrono" selected>', html)

        from facturacion_electronica.services.envio_lote import guardar_modo_envio

        guardar_modo_envio(MODO_ENVIO_LOTE)
        html = client.get('/facturacion-electronica/configuracion').get_data(as_text=True)
        self.assertIn('<option value="lote" selected>', html)


if __name__ == '__main__':
    unittest.main()
