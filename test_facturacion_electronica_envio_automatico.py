import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from app import create_app, db


class TestFacturacionElectronicaEnvioAutomatico(unittest.TestCase):
    """Cubre el job de envío automático (facturacion_electronica/services/envio_automatico.py)
    que reemplaza el flujo 100% manual: sin él, nadie enviaría los DE a SIFEN dentro
    de la ventana de 72h que exige el estándar."""

    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Cliente, SesionCaja, Usuario

        admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(admin)
        self.cliente = db.session.get(Cliente, 1)
        self.assertIsNotNone(self.cliente)

        sesion = SesionCaja(
            id_caja=1, id_usuario=admin.id_usuario, monto_inicial=0, estado='abierta',
        )
        db.session.add(sesion)
        db.session.commit()
        self.sesion = sesion

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _config_completa(self):
        from facturacion_electronica.models import FacturacionElectronicaConfig

        config = FacturacionElectronicaConfig.obtener()
        config.ruc = '4281292'
        config.dv_ruc = '5'
        config.razon_social = 'Empresa de Prueba'
        config.timbrado_numero = '12345678'
        config.timbrado_fecha_inicio = date(2026, 1, 1)
        config.establecimiento = '001'
        config.punto_expedicion = '001'
        config.actividad_economica_codigo = '1'
        config.cert_path = '/fake/cert.p12'
        config.cert_password = 'clave'
        config.csc = 'ABCD0000000000000000000000000000'
        config.csc_id = '0001'
        db.session.commit()
        return config

    def _venta(self, fecha_venta):
        from app.models import Venta

        venta = Venta(
            id_cliente=self.cliente.id_cliente,
            id_sesion_caja=self.sesion.id_sesion,
            subtotal=100000,
            total=100000,
            fecha_venta=fecha_venta,
        )
        db.session.add(venta)
        db.session.commit()
        return venta

    def test_cancelacion_pendiente_se_sigue_consultando(self):
        """Una baja pedida a la API queda en CANCELLATION_PENDING y de nuestro
        lado sigue siendo 'aprobado'. Si el job no la vuelve a mirar, la factura
        figura aprobada para siempre despues de haberla anulado."""
        from facturacion_electronica import ESTADO_APROBADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        venta = self._venta(datetime.utcnow())
        documento = DocumentoElectronico(
            id_venta=venta.id_venta,
            estado=ESTADO_APROBADO,
            respuesta_codigo='CANCELLATION_PENDING',
            cdc='0' * 44,
        )
        db.session.add(documento)

        aprobado_y_listo = DocumentoElectronico(
            id_venta=self._venta(datetime.utcnow()).id_venta,
            estado=ESTADO_APROBADO,
            respuesta_codigo='0260',
            cdc='1' * 44,
        )
        db.session.add(aprobado_y_listo)
        db.session.commit()

        vistos = []
        with patch('facturacion_electronica.services.envio_automatico.avanzar_documento',
                   lambda doc: vistos.append(doc.id) or None):
            resumen = procesar_pendientes()

        self.assertEqual(vistos, [documento.id])
        self.assertEqual(resumen['procesados'], 1)


    def _config_api(self):
        from facturacion_electronica.models import FacturacionElectronicaConfig

        config = FacturacionElectronicaConfig.obtener()
        config.proveedor = 'api'
        config.api_url = 'https://api.ejemplo.test'
        config.api_client_id = 'cli'
        config.api_credenciales = 'secreto'
        config.establecimiento = '001'
        config.punto_expedicion = '001'
        db.session.commit()
        return config

    def test_con_la_api_caida_el_job_sigue_mirando_los_documentos(self):
        """Una caida pasajera del proveedor no puede apagar el job entero.

        La compuerta de arranque (`validar_configuracion`) llego a preguntarle
        el certificado y el CSC a la API. Con su servicio abajo devolvia
        faltantes y `procesar_pendientes` cortaba antes de mirar un solo
        documento, devolviendo {0, 0, 0}: el scheduler solo loguea cuando hay
        procesados, asi que no quedaba rastro en ningun lado mientras la
        ventana de 72h de SIFEN seguia corriendo.
        """
        from facturacion_electronica import ESTADO_FIRMADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes
        from facturacion_electronica.services.proveedores.api_perfil import olvidar_perfil

        self._config_api()
        venta = self._venta(datetime.utcnow())
        doc = DocumentoElectronico(
            id_venta=venta.id_venta,
            estado=ESTADO_FIRMADO,
            cdc='0' * 44,
            establecimiento='001',
            punto='001',
            numero='0000001',
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
            respuesta_codigo='PENDING_BATCH',
        )
        db.session.add(doc)
        db.session.commit()

        olvidar_perfil()
        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   lambda *a, **k: (None, 'No se pudo conectar con la API.')):
            resumen = procesar_pendientes()

        self.assertEqual(resumen['procesados'], 1)
        self.assertEqual(resumen['error'], 1)
        db.session.refresh(doc)
        # El estado fiscal no se ensucia con un fallo de transporte: el DE
        # sigue siendo PENDING_BATCH del otro lado. Lo que importa es que el
        # job lo haya mirado y que el error se cuente, porque el scheduler
        # loguea el resumen cuando hubo procesados.
        self.assertEqual(doc.estado, ESTADO_FIRMADO)
        self.assertEqual(doc.respuesta_codigo, 'PENDING_BATCH')

    def test_documento_firmado_con_qr_se_envia_y_queda_aprobado(self):
        from facturacion_electronica import ESTADO_APROBADO, ESTADO_FIRMADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        venta = self._venta(datetime.utcnow())
        doc = DocumentoElectronico(
            id_venta=venta.id_venta,
            estado=ESTADO_FIRMADO,
            xml='<rDE/>',
            xml_firmado='<rDE Signature=1/>',
            xml_qr='<rDE gCamFuFD=1/>',
            codigo_seguridad='123456789',
        )
        db.session.add(doc)
        db.session.commit()

        respuesta_aprobada = {
            'rProtDe': {'dEstRes': 'Aprobado', 'dCodRes': '0260', 'dMsgRes': 'ok', 'dProtAut': '999'}
        }
        with patch(
            'facturacion_electronica.services.envio_service.enviar_de',
            return_value=(respuesta_aprobada, None),
        ) as mock_enviar:
            resumen = procesar_pendientes()

        mock_enviar.assert_called_once()
        self.assertEqual(resumen, {'procesados': 1, 'ok': 1, 'error': 0})
        db.session.refresh(doc)
        self.assertEqual(doc.estado, ESTADO_APROBADO)
        self.assertEqual(doc.protocolo_autorizacion, '999')

    def test_documento_de_venta_vieja_no_se_envia_y_queda_en_error(self):
        # Más de 720h desde la emisión: SIFEN lo rechazaría, así que el job no
        # debe ni intentar la llamada de red.
        from facturacion_electronica import ESTADO_ERROR, ESTADO_FIRMADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        venta_vieja = self._venta(datetime.utcnow() - timedelta(hours=750))
        doc = DocumentoElectronico(
            id_venta=venta_vieja.id_venta,
            estado=ESTADO_FIRMADO,
            xml='<rDE/>',
            xml_firmado='<rDE Signature=1/>',
            xml_qr='<rDE gCamFuFD=1/>',
            codigo_seguridad='123456789',
        )
        db.session.add(doc)
        db.session.commit()

        with patch('facturacion_electronica.services.envio_service.enviar_de') as mock_enviar:
            resumen = procesar_pendientes()

        mock_enviar.assert_not_called()
        self.assertEqual(resumen, {'procesados': 1, 'ok': 0, 'error': 1})
        db.session.refresh(doc)
        self.assertEqual(doc.estado, ESTADO_ERROR)

    def test_la_ventana_vencida_es_definitiva_y_el_job_deja_de_tocarlo(self):
        """El estado 'error' por si solo no frena al job: lo vuelve a tomar cada
        10 minutos del backoff, para siempre. Y esto no es un fallo transitorio,
        la fecha de emision ya paso. El costo real no es el trabajo al pedo sino
        el contador: cada pasada loguea 'error: N' y un error nuevo de verdad
        queda tapado en ese numero."""
        from facturacion_electronica import ESTADO_ERROR, ESTADO_FIRMADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.emision_service import SIN_REINTENTO
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        venta_vieja = self._venta(datetime.utcnow() - timedelta(hours=750))
        doc = DocumentoElectronico(
            id_venta=venta_vieja.id_venta,
            estado=ESTADO_FIRMADO,
            xml='<rDE/>',
            xml_firmado='<rDE Signature=1/>',
            xml_qr='<rDE gCamFuFD=1/>',
            codigo_seguridad='123456789',
        )
        db.session.add(doc)
        db.session.commit()

        with patch('facturacion_electronica.services.envio_service.enviar_de'):
            primera = procesar_pendientes()

        self.assertEqual(primera['procesados'], 1)
        db.session.refresh(doc)
        self.assertEqual(doc.estado, ESTADO_ERROR)
        self.assertEqual(doc.reintentar_despues, SIN_REINTENTO)

        # La pasada siguiente ya ni lo mira: ni procesado, ni sumando al
        # contador de errores.
        with patch('facturacion_electronica.services.envio_service.enviar_de') as mock_enviar:
            segunda = procesar_pendientes()

        mock_enviar.assert_not_called()
        self.assertEqual(segunda, {'procesados': 0, 'ok': 0, 'error': 0})

    def test_limpiar_la_marca_lo_vuelve_a_habilitar(self):
        """Poner reintentar_despues en NULL alcanza para reactivarlo, sin tocar
        codigo ni inventar un estado nuevo."""
        from facturacion_electronica import ESTADO_ERROR
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.emision_service import SIN_REINTENTO
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        venta = self._venta(datetime.utcnow())
        doc = DocumentoElectronico(
            id_venta=venta.id_venta,
            estado=ESTADO_ERROR,
            xml='<rDE/>',
            xml_firmado='<rDE Signature=1/>',
            xml_qr='<rDE gCamFuFD=1/>',
            codigo_seguridad='123456789',
            reintentar_despues=SIN_REINTENTO,
        )
        db.session.add(doc)
        db.session.commit()
        # 'error' arrastra ademas el backoff por updated_at; se lo saca de esa
        # ventana para que lo unico que lo frene sea la marca definitiva.
        doc.updated_at = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()

        self.assertEqual(procesar_pendientes()['procesados'], 0)

        doc.reintentar_despues = None
        doc.updated_at = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()

        with patch('facturacion_electronica.services.envio_service.enviar_de',
                   return_value=({'ns2:dCodRes': '0260', 'ns2:dEstRes': 'Aprobado'}, None)):
            self.assertEqual(procesar_pendientes()['procesados'], 1)

    def test_configuracion_incompleta_no_procesa_nada(self):
        from facturacion_electronica import ESTADO_FIRMADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        venta = self._venta(datetime.utcnow())
        doc = DocumentoElectronico(
            id_venta=venta.id_venta, estado=ESTADO_FIRMADO,
            xml='<rDE/>', xml_firmado='<f/>', xml_qr='<q/>', codigo_seguridad='123456789',
        )
        db.session.add(doc)
        db.session.commit()

        resumen = procesar_pendientes()
        self.assertEqual(resumen, {'procesados': 0, 'ok': 0, 'error': 0})

    def test_error_reciente_no_se_reintenta_de_inmediato(self):
        from facturacion_electronica import ESTADO_ERROR
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        venta = self._venta(datetime.utcnow())
        doc = DocumentoElectronico(
            id_venta=venta.id_venta, estado=ESTADO_ERROR,
            xml='<rDE/>', xml_firmado='<f/>', xml_qr='<q/>', codigo_seguridad='123456789',
        )
        db.session.add(doc)
        db.session.commit()  # updated_at queda en 'ahora' por el default onupdate

        with patch('facturacion_electronica.services.envio_service.enviar_de') as mock_enviar:
            resumen = procesar_pendientes()

        mock_enviar.assert_not_called()
        self.assertEqual(resumen, {'procesados': 0, 'ok': 0, 'error': 0})

    def _envejecer(self, documento, horas):
        """updated_at hacia atrás sin pasar por el ORM: el `onupdate` del modelo
        lo volvería a poner en 'ahora' y no habría forma de salir del backoff."""
        db.session.execute(
            db.text('UPDATE facturacion_electronica_documentos '
                    'SET updated_at = :cuando WHERE id = :id'),
            {'cuando': datetime.utcnow() - timedelta(hours=horas), 'id': documento.id},
        )
        db.session.commit()

    def test_errores_en_backoff_no_tapan_a_las_facturas_nuevas(self):
        """El backoff se filtra en el query, no salteando filas ya traídas.

        Con `limite` documentos en error permanente —una venta a crédito que la
        API no emite, un timbrado agotado— esos ocupaban los `limite` lugares
        del LIMIT, y la factura nueva, que tiene id más alto, no entraba nunca
        a la ventana: el job quedaba trancado sin que nada lo avisara.
        """
        from facturacion_electronica import ESTADO_ERROR, ESTADO_FIRMADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        for _ in range(3):
            db.session.add(DocumentoElectronico(
                id_venta=self._venta(datetime.utcnow()).id_venta, estado=ESTADO_ERROR,
            ))
        db.session.commit()  # updated_at = ahora: los tres están en backoff

        nueva = DocumentoElectronico(
            id_venta=self._venta(datetime.utcnow()).id_venta, estado=ESTADO_FIRMADO,
        )
        db.session.add(nueva)
        db.session.commit()

        vistos = []
        with patch('facturacion_electronica.services.envio_automatico.avanzar_documento',
                   lambda doc: vistos.append(doc.id) or None):
            resumen = procesar_pendientes(limite=3)

        self.assertEqual(vistos, [nueva.id])
        self.assertEqual(resumen['procesados'], 1)

    def test_error_viejo_si_se_reintenta(self):
        """La otra mitad del filtro nuevo: pasado el backoff tiene que volver."""
        from facturacion_electronica import ESTADO_ERROR
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        doc = DocumentoElectronico(
            id_venta=self._venta(datetime.utcnow()).id_venta, estado=ESTADO_ERROR,
        )
        db.session.add(doc)
        db.session.commit()
        self._envejecer(doc, horas=1)

        vistos = []
        with patch('facturacion_electronica.services.envio_automatico.avanzar_documento',
                   lambda documento: vistos.append(documento.id) or None):
            resumen = procesar_pendientes()

        self.assertEqual(vistos, [doc.id])
        self.assertEqual(resumen['procesados'], 1)


    def test_una_excepcion_no_impide_procesar_al_siguiente(self):
        """El docstring promete aislamiento por fila: si el primero revienta,
        el segundo igual tiene que avanzar."""
        from facturacion_electronica import ESTADO_FIRMADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        primero = DocumentoElectronico(
            id_venta=self._venta(datetime.utcnow()).id_venta, estado=ESTADO_FIRMADO,
        )
        segundo = DocumentoElectronico(
            id_venta=self._venta(datetime.utcnow()).id_venta, estado=ESTADO_FIRMADO,
        )
        db.session.add_all([primero, segundo])
        db.session.commit()

        vistos = []

        def _avanzar(documento):
            vistos.append(documento.id)
            if documento.id == primero.id:
                raise RuntimeError('fallo aislado de prueba')
            return None

        with patch('facturacion_electronica.services.envio_automatico.avanzar_documento',
                   _avanzar):
            resumen = procesar_pendientes()

        self.assertEqual(vistos, [primero.id, segundo.id])
        self.assertEqual(resumen, {'procesados': 2, 'ok': 1, 'error': 1})

    def test_venta_anulada_sin_de_remoto_no_se_emite(self):
        from facturacion_electronica import ESTADO_ERROR, ESTADO_GENERADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        venta = self._venta(datetime.utcnow())
        venta.estado = 'anulada'
        doc = DocumentoElectronico(
            id_venta=venta.id_venta, estado=ESTADO_GENERADO,
        )
        db.session.add(doc)
        db.session.commit()

        vistos = []
        with patch('facturacion_electronica.services.envio_automatico.avanzar_documento',
                   lambda documento: vistos.append(documento.id) or None):
            resumen = procesar_pendientes()

        self.assertEqual(vistos, [])
        self.assertEqual(resumen, {'procesados': 1, 'ok': 0, 'error': 1})
        db.session.refresh(doc)
        self.assertEqual(doc.estado, ESTADO_ERROR)
        self.assertIn('anulada', (doc.respuesta_mensaje or '').lower())

    def test_fallo_al_firmar_no_se_reintenta_en_cada_pasada(self):
        """Un fallo de firma dejaba el DE en 'generado', que no tiene backoff.

        Visto en el servidor de prueba: el mismo documento intentando firmarse
        cada 5 minutos para siempre, llenando el journal y sin dejar en la
        pantalla ni una palabra de por qué no avanzaba. El backoff por
        `updated_at` no lo tapaba porque sólo mira los que quedaron en 'error'.
        """
        from facturacion_electronica import ESTADO_GENERADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        venta = self._venta(datetime.utcnow())
        doc = DocumentoElectronico(
            id_venta=venta.id_venta, estado=ESTADO_GENERADO, xml='<rDE/>',
        )
        db.session.add(doc)
        db.session.commit()

        fallo = 'PKCS#12 MAC could not be verified. Invalid password?'
        with patch('facturacion_electronica.services.generacion_service.firmar_xml',
                   return_value=(None, fallo)) as mock_firmar:
            primera = procesar_pendientes()
            segunda = procesar_pendientes()

        # Una sola llamada: la segunda pasada ni miró el documento.
        mock_firmar.assert_called_once()
        self.assertEqual(primera['error'], 1)
        self.assertEqual(segunda['procesados'], 0)

        db.session.refresh(doc)
        # El estado fiscal no se ensucia, pero el motivo queda a la vista.
        self.assertEqual(doc.estado, ESTADO_GENERADO)
        self.assertIn('Invalid password', doc.respuesta_mensaje or '')
        self.assertIsNotNone(doc.reintentar_despues)

    def test_cumplido_el_backoff_el_documento_vuelve_a_intentarse(self):
        """El backoff posterga, no descarta: si el Node vuelve, el DE sigue."""
        from facturacion_electronica import ESTADO_FIRMADO, ESTADO_GENERADO
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        self._config_completa()
        venta = self._venta(datetime.utcnow())
        doc = DocumentoElectronico(
            id_venta=venta.id_venta,
            estado=ESTADO_GENERADO,
            xml='<rDE/>',
            respuesta_mensaje='El servicio no respondió.',
            reintentar_despues=datetime.utcnow() - timedelta(minutes=1),
        )
        db.session.add(doc)
        db.session.commit()

        with patch('facturacion_electronica.services.generacion_service.firmar_xml',
                   return_value=('<rDE Signature=1/>', None)), \
             patch('facturacion_electronica.services.generacion_service.generar_qr',
                   return_value=('<rDE gCamFuFD=1/>', None)), \
             patch('facturacion_electronica.services.envio_service.enviar_de',
                   return_value=({'rProtDe': {'dEstRes': 'Aprobado'}}, None)):
            resumen = procesar_pendientes()

        self.assertEqual(resumen['procesados'], 1)
        db.session.refresh(doc)
        self.assertNotEqual(doc.estado, ESTADO_GENERADO)
        # Avanzó: el freno de la pasada anterior no queda pegado.
        self.assertIsNone(doc.reintentar_despues)


if __name__ == '__main__':
    unittest.main()
