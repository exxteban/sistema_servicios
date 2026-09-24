"""Switch de proveedor de FE: configuración y emisión por API.

Los tests del **motor propio** no se tocan: corren con el proveedor por
defecto ('propio'). Acá se prueba el otro lado del switch y, sobre todo, los
dos invariantes que no se pueden romper en silencio:

- la numeración sigue siendo nuestra también con la API (su contrato exige
  `document_number`), y un fallo de red no puede consumir dos correlativos;
- con la API activa no se llama nunca al motor propio (Node/TIPS/certificado).

El resto del circuito está en `..._proveedor_documentos.py` (lote, notas de
crédito, formas de pago) y `..._proveedor_ciclo.py` (rechazo, KuDE, baja).
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import db
from facturacion_electronica import ESTADO_APROBADO, ESTADO_ERROR, ESTADO_FIRMADO
from facturacion_electronica.models import FacturacionElectronicaConfig
from facturacion_electronica.services import validar_configuracion, validar_readiness
from facturacion_electronica.services.proveedores import api_client


def _config_incompleta():
    return FacturacionElectronicaConfig(id=1, establecimiento='001', punto_expedicion='001')


# --------------------------------------------------------------- validación

def test_validacion_propia_pide_certificado_y_csc():
    faltantes = validar_configuracion(_config_incompleta())
    assert 'Certificado digital (.p12)' in faltantes
    assert 'CSC (Código de Seguridad del Contribuyente)' in faltantes
    assert 'URL de la API de facturación electrónica' not in faltantes


def test_validacion_api_no_pide_certificado_ni_csc():
    config = _config_incompleta()
    config.proveedor = 'api'
    faltantes = validar_configuracion(config)
    assert 'Certificado digital (.p12)' not in faltantes
    assert 'CSC (Código de Seguridad del Contribuyente)' not in faltantes
    assert 'URL de la API de facturación electrónica' in faltantes
    assert 'Client ID de la API' in faltantes
    assert 'Client Secret de la API' in faltantes


def test_validacion_api_completa_no_falta_nada():
    from facturacion_electronica.services.proveedores.api_perfil import olvidar_perfil

    config = FacturacionElectronicaConfig(
        id=1, proveedor='api', establecimiento='001', punto_expedicion='001',
        api_url='https://api.ejemplo.test', api_client_id='cli',
        api_credenciales='secreto',
    )
    perfil = {
        'ruc': '',
        'sifen_config': {
            'certificate': {'fingerprint_sha256': 'abc'},
            'csc': 'configured',
        },
        'stamps': [],
    }
    olvidar_perfil()
    with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
               lambda *a, **k: (perfil, None)):
        assert validar_readiness(config) == []


# ------------------------------------------------------------- transporte

def test_base_url_tolera_lo_que_pega_la_gente():
    for entrada, esperado in (
        ('https://fe.ejemplo.com', 'https://fe.ejemplo.com/api/v1'),
        ('https://fe.ejemplo.com/', 'https://fe.ejemplo.com/api/v1'),
        ('https://fe.ejemplo.com/api/v1', 'https://fe.ejemplo.com/api/v1'),
        ('https://fe.ejemplo.com/api/v1/docs', 'https://fe.ejemplo.com/api/v1'),
        ('https://fe.ejemplo.com/api/v1/docs/#/', 'https://fe.ejemplo.com/api/v1'),
        ('https://fe.mileniocreativo.com/api/v1/docs/#/', 'https://fe.mileniocreativo.com/api/v1'),
    ):
        config = SimpleNamespace(api_url=entrada)
        assert api_client.base_url(config) == esperado


def test_base_url_vacia_no_inventa_host():
    assert api_client.base_url(SimpleNamespace(api_url='')) == ''


# ------------------------------------------------------------------ payload

def test_payload_receptor_contribuyente_separa_ruc_y_dv():
    from facturacion_electronica.services.proveedores.api_payload import construir_receptor

    cliente = SimpleNamespace(
        id_cliente=7, ruc_ci='80012345-6', nombre='Ferretería SA',
        email=None, direccion=None, telefono=None,
    )
    receptor = construir_receptor(cliente)
    assert receptor['nature'] == 1
    assert receptor['ruc'] == '80012345'
    assert receptor['dv'] == 6
    assert receptor['contributor_type'] == 2


def test_payload_receptor_consumidor_final_es_innominado():
    from facturacion_electronica.services.proveedores.api_payload import construir_receptor

    cliente = SimpleNamespace(
        id_cliente=1, ruc_ci='', nombre='Consumidor Final',
        email=None, direccion=None, telefono=None,
    )
    receptor = construir_receptor(cliente)
    assert receptor['nature'] == 2
    assert receptor['id_type'] == 5
    assert receptor['id_number'] == '0'


from test_facturacion_electronica_proveedor_base import BaseProveedorApi, respuesta_api


# --------------------------------------------------------------- integración

class TestProveedorApi(BaseProveedorApi):
    def test_emision_feliz_guarda_cdc_y_no_usa_el_motor_propio(self):
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        llamadas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            llamadas.append((metodo, ruta, kwargs.get('json'), kwargs.get('headers')))
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta == '/sifen/electronic-documents/':
                return respuesta_api(), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar), \
                patch('facturacion_electronica.services.sifen_client.generar_xml') as mock_xml:
            documento, error = emitir_para_pos(self._venta())

        self.assertIsNone(error)
        mock_xml.assert_not_called()
        self.assertEqual(documento.cdc, '0' * 44)
        self.assertEqual(documento.api_documento_id, 'd0c0ffee-0000-4000-8000-000000000001')
        self.assertEqual(documento.estado, ESTADO_FIRMADO)
        # El número lo ponemos nosotros: la API lo exige en el alta.
        self.assertEqual(documento.numero, '0000001')
        alta = [c for c in llamadas if c[1] == '/sifen/electronic-documents/'][0]
        self.assertEqual(alta[2]['document_number'], '0000001')
        self.assertEqual(alta[2]['stamp'], 'aaaaaaaa-0000-4000-8000-000000000001')
        self.assertTrue(alta[3]['Idempotency-Key'])

    def test_no_emite_factura_de_una_venta_anulada(self):
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos
        from facturacion_electronica.services.numeracion_service import peek_proximo_numero

        self._activar_api()
        venta = self._venta()
        venta.estado = 'anulada'
        db.session.commit()
        proximo_antes = peek_proximo_numero('001', '001')

        def _solicitar(config, metodo, ruta, **kwargs):
            raise AssertionError(f'no se debe llamar a la API para una venta anulada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = emitir_para_pos(venta)

        self.assertIsNone(documento)
        self.assertIn('anulada', (error or '').lower())
        self.assertEqual(peek_proximo_numero('001', '001'), proximo_antes)

    def test_emision_no_avanza_sin_timbrado_para_el_punto(self):
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        perfil = self._perfil()
        perfil['stamps'][0]['expedition_point'] = '002'

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return perfil, None
            raise AssertionError('no se debe intentar el alta sin timbrado')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = emitir_para_pos(self._venta())

        self.assertIn('001-001', error)
        self.assertEqual(documento.estado, ESTADO_ERROR)

    def test_ruc_distinto_al_de_la_api_frena_la_emision(self):
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        config = self._activar_api()
        config.ruc = '80099999'
        db.session.commit()

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   lambda *a, **k: (self._perfil(), None)):
            documento, error = emitir_para_pos(self._venta())

        self.assertIn('no coincide', error)
        self.assertEqual(documento.estado, ESTADO_ERROR)

    # -- fallos ------------------------------------------------------------

    def test_caida_de_red_no_consume_dos_correlativos(self):
        from facturacion_electronica.services.numeracion_service import peek_proximo_numero
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        venta = self._venta()

        def _caido(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if metodo == 'GET':  # la búsqueda de recuperación tampoco lo encuentra
                return {'results': []}, None
            return None, 'No se pudo conectar con la API de facturación electrónica.'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _caido):
            documento, error = emitir_para_pos(venta)
            primero = documento.numero
            documento, error = emitir_para_pos(venta)

        self.assertIsNotNone(error)
        self.assertEqual(documento.numero, primero)
        self.assertEqual(peek_proximo_numero('001', '001'), '0000002')

    def test_alta_perdida_se_recupera_por_idempotencia(self):
        """El POST llegó y la respuesta se perdió: el reintento adopta el documento."""
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        venta = self._venta()
        estado = {'clave': None}

        def _primera(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta.startswith('/sifen/electronic-documents/?'):
                return {'results': []}, None
            estado['clave'] = kwargs['headers']['Idempotency-Key']
            return None, 'La API tardó demasiado en responder.'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _primera):
            documento, error = emitir_para_pos(venta)
        self.assertIsNotNone(error)
        self.assertIsNone(documento.api_documento_id)

        def _segunda(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta.startswith('/sifen/electronic-documents/?'):
                return {'results': [respuesta_api(idempotency_key=estado['clave'])]}, None
            return None, 'La API tardó demasiado en responder.'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _segunda):
            documento, error = emitir_para_pos(venta)

        self.assertIsNone(error)
        self.assertEqual(documento.api_documento_id, 'd0c0ffee-0000-4000-8000-000000000001')

    def test_rechazo_de_la_api_queda_en_el_documento(self):
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()

        def _rechaza(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if metodo == 'GET':
                return {'results': []}, None
            return None, 'La API respondió 422: document_number: ya emitido'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _rechaza):
            documento, error = emitir_para_pos(self._venta())

        self.assertIn('422', error)
        self.assertEqual(documento.estado, ESTADO_ERROR)
        self.assertIn('422', documento.respuesta_mensaje)

    # -- job ----------------------------------------------------------------

    def test_job_con_api_no_entra_al_circuito_propio(self):
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._activar_api()
        doc = DocumentoElectronico(
            id_venta=self._venta().id_venta,
            estado=ESTADO_FIRMADO,
            cdc='0' * 44,
            numero='0000001',
            establecimiento='001',
            punto='001',
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
        )
        db.session.add(doc)
        db.session.commit()

        rutas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            rutas.append((metodo, ruta))
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta.endswith('/electronic-documents/d0c0ffee-0000-4000-8000-000000000001/'):
                return respuesta_api(), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar), \
                patch('facturacion_electronica.services.emision_service.enviar_de') as mock_enviar:
            resumen = procesar_pendientes()

        mock_enviar.assert_not_called()
        self.assertEqual(resumen, {'procesados': 1, 'ok': 1, 'error': 0})
        # El lote lo arma y lo envia su pipeline solo, cada 30 segundos y por
        # empresa. Empujarlo a mano no adelanta nada y, con dos locales sobre
        # las mismas credenciales, cada uno lotearia los documentos del otro.
        self.assertEqual(
            [r for r in rutas if r[1] != '/sifen/me/'],
            [('GET', '/sifen/electronic-documents/d0c0ffee-0000-4000-8000-000000000001/')],
        )

    def test_sandbox_de_la_api_no_se_reintenta_para_siempre(self):
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.proveedores.fachada import avanzar_documento

        self._activar_api()
        doc = DocumentoElectronico(
            id_venta=self._venta().id_venta,
            estado=ESTADO_FIRMADO,
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
        )
        db.session.add(doc)
        db.session.commit()

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta.endswith('/electronic-documents/d0c0ffee-0000-4000-8000-000000000001/'):
                return respuesta_api(transmits=False), None
            raise AssertionError('no se debe intentar armar lote en sandbox')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            error = avanzar_documento(doc)

        self.assertIn('sandbox', error)
        self.assertEqual(doc.estado, ESTADO_ERROR)

    def test_aprobacion_trae_el_protocolo(self):
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.proveedores.fachada import consultar_documento

        self._activar_api()
        doc = DocumentoElectronico(
            id_venta=self._venta().id_venta,
            estado=ESTADO_FIRMADO,
            cdc='0' * 44,
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
        )
        db.session.add(doc)
        db.session.commit()

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta.startswith('/sifen/lookup/cdc/'):
                return {'prot_aut': '123456789', 'sifen_code': '0260'}, None
            return respuesta_api('APPROVED'), None

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            _respuesta, error = consultar_documento(doc)

        self.assertIsNone(error)
        self.assertEqual(doc.estado, ESTADO_APROBADO)
        self.assertEqual(doc.protocolo_autorizacion, '123456789')

    # -- configuración -------------------------------------------------------

    def test_no_se_cambia_proveedor_con_documentos_transmitidos(self):
        from facturacion_electronica import ESTADO_APROBADO as APROBADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.config_service import guardar_configuracion

        config = FacturacionElectronicaConfig.obtener()
        self.assertEqual(config.proveedor, 'propio')

        db.session.add(DocumentoElectronico(
            id_venta=self._venta().id_venta, estado=APROBADO, cdc='0' * 44,
        ))
        db.session.commit()

        _config, error = guardar_configuracion({'proveedor': 'api'})
        self.assertIn('transmitidos a SIFEN', error)
        self.assertEqual(FacturacionElectronicaConfig.obtener().proveedor, 'propio')

    def test_las_pruebas_que_nunca_salieron_no_bloquean_el_cambio(self):
        """Un documento en generado/firmado/error nunca llegó a SIFEN: no ata
        la instalación a ningún proveedor."""
        from facturacion_electronica import ESTADO_FIRMADO as FIRMADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.config_service import guardar_configuracion

        venta = self._venta()
        db.session.add(DocumentoElectronico(id_venta=venta.id_venta, estado=FIRMADO))
        db.session.add(DocumentoElectronico(id_venta=venta.id_venta, estado=ESTADO_ERROR))
        db.session.commit()

        _config, error = guardar_configuracion({
            'proveedor': 'api',
            'api_url': 'https://api.ejemplo.test',
            'api_client_id': 'cliente-test',
            'api_credenciales': 'secreto',
        })
        self.assertIsNone(error)
        self.assertEqual(FacturacionElectronicaConfig.obtener().proveedor, 'api')

    def test_lo_transmitido_en_prueba_no_bloquea_el_cambio(self):
        """Una demo aprobada en SIFEN test, por cualquiera de los dos
        proveedores, no tiene validez fiscal: no ata la instalación."""
        from facturacion_electronica import AMBIENTE_TEST, ESTADO_APROBADO as APROBADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.config_service import guardar_configuracion

        venta = self._venta()
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, estado=APROBADO, cdc='0' * 44, ambiente=AMBIENTE_TEST,
        ))
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, estado=ESTADO_FIRMADO, cdc='1' * 44,
            api_documento_id='d0c0ffee-0000-4000-8000-000000000002', ambiente=AMBIENTE_TEST,
        ))
        db.session.commit()

        _config, error = guardar_configuracion({
            'proveedor': 'api',
            'api_url': 'https://api.ejemplo.test',
            'api_client_id': 'cliente-test',
            'api_credenciales': 'secreto',
        })
        self.assertIsNone(error)
        self.assertEqual(FacturacionElectronicaConfig.obtener().proveedor, 'api')

    def test_lo_transmitido_en_produccion_si_bloquea_el_cambio(self):
        from facturacion_electronica import AMBIENTE_PRODUCCION, ESTADO_APROBADO as APROBADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.config_service import guardar_configuracion

        db.session.add(DocumentoElectronico(
            id_venta=self._venta().id_venta, estado=APROBADO, cdc='0' * 44,
            ambiente=AMBIENTE_PRODUCCION,
        ))
        db.session.commit()

        _config, error = guardar_configuracion({'proveedor': 'api'})
        self.assertIn('transmitidos a SIFEN', error)
        self.assertEqual(FacturacionElectronicaConfig.obtener().proveedor, 'propio')

    def test_no_se_cambia_proveedor_con_de_remoto_pendiente(self):
        """En la API, firmado = PENDING_BATCH: ya hay CDC del otro lado."""
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.config_service import guardar_configuracion

        config = FacturacionElectronicaConfig.obtener()
        self.assertEqual(config.proveedor, 'propio')

        db.session.add(DocumentoElectronico(
            id_venta=self._venta().id_venta,
            estado=ESTADO_FIRMADO,
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
            cdc='0' * 44,
        ))
        db.session.commit()

        _config, error = guardar_configuracion({'proveedor': 'api'})
        self.assertIn('transmitidos a SIFEN', error)
        self.assertEqual(FacturacionElectronicaConfig.obtener().proveedor, 'propio')

    def test_guardar_api_cifra_el_secreto(self):
        from facturacion_electronica.services.config_service import guardar_configuracion
        from facturacion_electronica.services.crypto import descifrar

        _config, error = guardar_configuracion({
            'proveedor': 'api',
            'api_url': 'https://api.ejemplo.test',
            'api_client_id': 'cliente-test',
            'api_credenciales': 'token-secreto',
        })
        self.assertIsNone(error)
        config = FacturacionElectronicaConfig.obtener()
        self.assertEqual(config.proveedor, 'api')
        self.assertEqual(config.api_client_id, 'cliente-test')
        self.assertNotEqual(config.api_credenciales, 'token-secreto')
        self.assertEqual(descifrar(config.api_credenciales), 'token-secreto')

    def test_sincronizar_emisor_copia_los_datos_de_la_api(self):
        from facturacion_electronica.services.proveedores.fachada import sincronizar_emisor

        config = self._activar_api()
        perfil = self._perfil()
        perfil.update({
            'legal_name': 'Comercial Ejemplo SA',
            'dv': 6,
            'address': 'Avda. Siempreviva 742',
            'phone': '021 000 000',
            'email': 'facturacion@ejemplo.test',
        })

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   lambda *a, **k: (perfil, None)):
            resumen, error = sincronizar_emisor(config)

        self.assertIsNone(error)
        self.assertIn('12345678', resumen)
        config = FacturacionElectronicaConfig.obtener()
        self.assertEqual(config.razon_social, 'Comercial Ejemplo SA')
        self.assertEqual(config.ruc, '80012345')
        self.assertEqual(config.dv_ruc, '6')
        self.assertEqual(config.timbrado_numero, '12345678')


if __name__ == '__main__':
    unittest.main()
