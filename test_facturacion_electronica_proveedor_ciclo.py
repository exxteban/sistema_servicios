"""Cierre del circuito del proveedor API: rechazo, impresión y baja.

Continuación de `test_facturacion_electronica_proveedor.py`; comparte su
andamiaje. Acá está el final del camino de un documento: el motivo real de un
rechazo de SIFEN (que no está en los eventos del DE), el KuDE con su identidad
histórica, quién puede imprimirlo, el piso de numeración del timbrado y la
cancelación que no puede darse por hecha.
"""
import unittest
from unittest.mock import patch

from app import db
from facturacion_electronica import ESTADO_APROBADO, ESTADO_FIRMADO
from facturacion_electronica.models import FacturacionElectronicaConfig

from test_facturacion_electronica_proveedor_base import BaseProveedorApi, respuesta_api


class TestProveedorApiCiclo(BaseProveedorApi):
    # -- el rechazo con su motivo ------------------------------------------

    def test_el_rechazo_trae_el_motivo_de_sifen(self):
        """El documento sólo dice `REJECTED` / "Rechazado": el código y el
        mensaje de SIFEN están en el ítem del lote, no en los eventos del DE.

        `GET /electronic-documents/{id}/events/` sólo lista cancelación,
        inutilización y nominación. El result de la emisión está en
        `SifenBatchRead.items[].result`; el log `GET /events/` apunta al lote
        con `batch.processed`.
        """
        from facturacion_electronica import ESTADO_RECHAZADO
        from facturacion_electronica.services.proveedores.api import ProveedorApi

        self._activar_api()
        documento = self._documento_en_lote(1)
        lote_id = 'b0c0ffee-0000-4000-8000-000000000002'
        rutas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            rutas.append(ruta)
            if ruta.startswith('/events/'):
                return {
                    'results': [{
                        'event_type': 'batch.processed',
                        'resource_type': 'batch',
                        'resource_id': lote_id,
                        'payload': {'document_id': documento.api_documento_id},
                    }],
                    'next_cursor': 1, 'epoch': 1, 'min_available_seq': 0,
                }, None
            if ruta == f'/sifen/batches/{lote_id}/':
                return {
                    'id': lote_id,
                    'items': [{
                        'document_id': documento.api_documento_id,
                        'document_status': 'REJECTED',
                        'result': {'gResProc': [
                            {'dCodRes': '0420', 'dMsgRes': 'RUC del receptor no existe'},
                        ]},
                    }],
                }, None
            if '/electronic-documents/' in ruta and '/events/' in ruta:
                raise AssertionError('el rechazo de emisión no está en los eventos del DE')
            if ruta.startswith('/sifen/electronic-documents/'):
                return respuesta_api(estado='REJECTED'), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            ProveedorApi().avanzar(documento)

        self.assertEqual(documento.estado, ESTADO_RECHAZADO)
        self.assertIn('0420', documento.respuesta_mensaje)
        self.assertIn('RUC del receptor no existe', documento.respuesta_mensaje)
        self.assertEqual(documento.respuesta_codigo, 'REJECTED')
        self.assertEqual(documento.api_lote_id, lote_id)
        self.assertTrue(any(ruta.startswith('/events/') for ruta in rutas))
        self.assertTrue(any(ruta.startswith('/sifen/batches/') for ruta in rutas))
        self.assertFalse(any(
            '/electronic-documents/' in ruta and '/events/' in ruta for ruta in rutas
        ))

    def test_un_documento_aprobado_no_va_a_buscar_eventos(self):
        """La llamada extra es sólo para el rechazo."""
        from facturacion_electronica.services.proveedores.api import ProveedorApi

        self._activar_api()
        documento = self._documento_en_lote(1)
        rutas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            rutas.append(ruta)
            if ruta.startswith('/sifen/lookup/cdc/'):
                return {'prot_aut': '999'}, None
            if ruta.startswith('/sifen/electronic-documents/'):
                return respuesta_api(estado='APPROVED'), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            ProveedorApi().avanzar(documento)

        self.assertEqual(documento.estado, ESTADO_APROBADO)
        self.assertFalse(any('/events/' in ruta for ruta in rutas))

    def test_el_kude_conserva_prueba_y_timbrado_historicos(self):
        """Reimprimir una factura de prueba en producción no puede perder la
        leyenda ni mostrar el timbrado nuevo: esos datos salen del documento."""
        from facturacion_electronica import AMBIENTE_PRODUCCION, AMBIENTE_TEST
        from facturacion_electronica.models import FacturacionElectronicaConfig
        from facturacion_electronica.services.kude_service import construir_contexto_kude
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        config = self._activar_api()
        config.ambiente = AMBIENTE_PRODUCCION
        config.timbrado_numero = '99999999'
        db.session.commit()
        venta = self._venta()

        def _solicitar(config_api, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                perfil = self._perfil()
                perfil['sifen_mode'] = 'test'
                return perfil, None
            if ruta == '/sifen/electronic-documents/':
                return respuesta_api(origin_mode='test'), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = emitir_para_pos(venta)

        self.assertIsNone(error)
        self.assertEqual(documento.ambiente, AMBIENTE_TEST)
        self.assertEqual(documento.timbrado, '12345678')

        config = FacturacionElectronicaConfig.obtener()
        config.ambiente = AMBIENTE_PRODUCCION
        config.timbrado_numero = '88888888'
        db.session.commit()

        ctx = construir_contexto_kude(venta, documento)
        self.assertFalse(ctx['es_produccion'])
        self.assertEqual(ctx['timbrado_numero'], '12345678')

    def test_el_cajero_puede_imprimir_el_kude(self):
        """emitir-pos sólo pide login; el KuDE no puede exigir admin."""
        from app.models import Rol, Usuario
        from facturacion_electronica.models import DocumentoElectronico

        venta = self._venta()
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=1, numero='0000001',
            estado=ESTADO_FIRMADO, cdc='0' * 44, ambiente='test',
            timbrado='12345678',
        ))
        rol = Rol.query.filter_by(nombre='Cajero').first()
        cajero = Usuario(
            username='cajero_kude', nombre_completo='Cajero KuDE',
            id_rol=rol.id_rol, activo=True,
        )
        cajero.set_password('test1234')
        db.session.add(cajero)
        db.session.commit()

        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(cajero.id_usuario)
            sess['_fresh'] = True
        response = client.get(f'/facturacion-electronica/kude/{venta.id_venta}')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('FACTURA ELECTRÓNICA', html)
        self.assertIn('SIN VALIDEZ FISCAL', html)

    def test_estado_pos_recupera_el_kude_si_ya_hay_de(self):
        """Si el POST del POS se aborta, un GET tiene que ver la factura emitida."""
        from app.models import Rol, Usuario
        from facturacion_electronica.models import DocumentoElectronico

        venta = self._venta()
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=1, numero='0000001',
            estado=ESTADO_FIRMADO, cdc='0' * 44,
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
        ))
        rol = Rol.query.filter_by(nombre='Cajero').first()
        cajero = Usuario(
            username='cajero_estado', nombre_completo='Cajero estado',
            id_rol=rol.id_rol, activo=True,
        )
        cajero.set_password('test1234')
        db.session.add(cajero)
        db.session.commit()

        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(cajero.id_usuario)
            sess['_fresh'] = True
        response = client.get(f'/facturacion-electronica/estado-pos/{venta.id_venta}')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['cdc'], '0' * 44)
        self.assertIn(f'/facturacion-electronica/kude/{venta.id_venta}', data['kude_url'])

    # -- el piso de numeración del timbrado --------------------------------

    def test_la_sincro_sube_el_correlativo_al_piso_del_timbrado(self):
        """`dNumIni` es el primer número que el timbrado reserva, y no siempre
        es 1: un cliente que ya venía facturando arranca donde quedó. Nuestro
        contador nace en 0, así que sin esto la primera factura saldría
        0000001 — fuera del rango declarado — y SIFEN la rechaza."""
        from facturacion_electronica.services.numeracion_service import peek_proximo_numero
        from facturacion_electronica.services.proveedores.fachada import sincronizar_emisor

        config = self._activar_api()
        perfil = self._perfil()
        perfil['stamps'][0]['initial_number'] = '0000501'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   lambda *a, **k: (perfil, None)):
            resumen, error = sincronizar_emisor(config)

        self.assertIsNone(error)
        self.assertIn('0000501', resumen)
        self.assertEqual(peek_proximo_numero('001', '001'), '0000501')

    def test_el_piso_del_timbrado_nunca_baja_el_correlativo(self):
        """Bajarlo repetiría números ya emitidos sobre el mismo timbrado."""
        from facturacion_electronica.services.numeracion_service import (
            ajustar_secuencia,
            peek_proximo_numero,
        )
        from facturacion_electronica.services.proveedores.fachada import sincronizar_emisor

        config = self._activar_api()
        ajustar_secuencia('001', '001', 900)
        perfil = self._perfil()
        perfil['stamps'][0]['initial_number'] = '0000501'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   lambda *a, **k: (perfil, None)):
            resumen, _error = sincronizar_emisor(config)

        self.assertNotIn('0000501', resumen)
        self.assertEqual(peek_proximo_numero('001', '001'), '0000901')

    # -- lo que se le dice al usuario al anular ----------------------------

    def test_la_cancelacion_pendiente_no_se_anuncia_como_hecha(self):
        """La API deja la baja en CANCELLATION_PENDING hasta que SIFEN
        contesta, y mientras tanto el DE sigue vigente. Decir "podés volver a
        facturar" era mentira: la re-emisión se niega con "ya está aprobado" y
        nadie entendía por qué."""
        from flask import get_flashed_messages
        from flask_login import login_user

        from app.models import Usuario
        from facturacion_electronica import TIPO_FACTURA
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.routes import cancelar

        self._activar_api()
        venta = self._venta()
        documento = DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA, numero='0000001',
            estado=ESTADO_APROBADO, cdc='0' * 44,
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
        )
        db.session.add(documento)
        db.session.commit()

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta.endswith('/cancel/'):
                return {'id': 'evento-1'}, None
            # La consulta posterior: SIFEN todavía no confirmó la baja.
            return respuesta_api(estado='CANCELLATION_PENDING'), None

        admin = Usuario.query.filter_by(username='admin').first()
        with self.app.test_request_context(
            '/facturacion-electronica/cancelar/%d' % venta.id_venta,
            method='POST', data={'motivo': 'Error de carga en el detalle'},
        ):
            login_user(admin)
            with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                       _solicitar):
                cancelar(venta.id_venta)
            mensajes = ' '.join(get_flashed_messages())

        self.assertNotIn('Podés volver a facturar', mensajes)
        self.assertIn('todavía no la confirmó', mensajes)
        self.assertEqual(documento.estado, ESTADO_APROBADO)

    def test_cancelacion_aceptada_se_conserva_si_falla_el_get(self):
        """Si el POST de baja entra y el GET posterior cae, el job tiene que
        seguir viendo CANCELLATION_PENDING. Sin eso el DE queda APPROVED y
        nadie lo vuelve a mirar."""
        from facturacion_electronica import ESTADO_API_CANCELACION_PENDIENTE
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.proveedores.fachada import cancelar_documento

        self._activar_api()
        venta = self._venta()
        documento = DocumentoElectronico(
            id_venta=venta.id_venta, numero='0000001',
            estado=ESTADO_APROBADO, cdc='0' * 44,
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
            respuesta_codigo='APPROVED',
        )
        db.session.add(documento)
        db.session.commit()

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta.endswith('/cancel/'):
                return {'id': 'evento-1'}, None
            return None, 'timeout al consultar el documento'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   _solicitar):
            doc, error = cancelar_documento(documento, 'Error de carga en el detalle')

        self.assertIsNone(error)
        self.assertEqual(doc.estado, ESTADO_APROBADO)
        self.assertEqual(doc.respuesta_codigo, ESTADO_API_CANCELACION_PENDIENTE)
        self.assertEqual(doc.motivo_cancelacion, 'Error de carga en el detalle')

    def test_no_se_anula_venta_con_de_remoto_pendiente(self):
        from app.models import Usuario
        from facturacion_electronica.models import DocumentoElectronico

        self._activar_api()
        venta = self._venta()
        db.session.add(DocumentoElectronico(
            id_venta=venta.id_venta,
            estado=ESTADO_FIRMADO,
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
            cdc='0' * 44,
        ))
        db.session.commit()

        admin = Usuario.query.filter_by(username='admin').first()
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin.id_usuario)
            sess['_fresh'] = True
        response = client.post(f'/ventas/{venta.id_venta}/anular', data={})
        self.assertEqual(response.status_code, 302)
        db.session.refresh(venta)
        self.assertNotEqual(venta.estado, 'anulada')

    def test_el_kude_de_la_api_imprime_el_redondeo_que_informo(self):
        """Desde la API 1.20.0 el DE sale con dRedon y la API lo informa en
        `totals.rounding`: el papel imprime ése, no uno calculado acá."""
        import json

        from facturacion_electronica.services.kude_service import construir_contexto_kude

        self._activar_api()
        documento = self._documento_en_lote(1)
        documento.respuesta_raw = json.dumps({'totals': {'rounding': '43'}})
        venta = documento.venta
        venta.total = 993343
        db.session.commit()

        contexto = construir_contexto_kude(venta, documento)
        self.assertEqual(contexto['total'], 993300)
        self.assertEqual(contexto['redondeo'], 43)

    def test_el_kude_de_la_api_no_imprime_redondeo(self):
        """Un DE de la API sin `totals.rounding` (los anteriores a su 1.20.0)
        salió crudo. El papel decía 993.300 y el documento en SIFEN 993.343
        (venta #112 de Janelipy)."""
        from facturacion_electronica.services.kude_service import construir_contexto_kude

        self._activar_api()
        documento = self._documento_en_lote(1)
        venta = documento.venta
        venta.total = 993343
        db.session.commit()

        contexto = construir_contexto_kude(venta, documento)
        self.assertEqual(contexto['total'], 993343)
        self.assertEqual(contexto['redondeo'], 0)

        # Un DE del motor propio (sin id en la API) conserva su redondeo.
        documento.api_documento_id = None
        contexto = construir_contexto_kude(venta, documento)
        self.assertEqual(contexto['total'], 993300)
        self.assertEqual(contexto['redondeo'], 43)

    def test_la_sincro_no_cambia_el_establecimiento_del_local(self):
        """Local 2 (002) de un cliente con dos locales, y en la API sólo está el
        timbrado de 001-001. Antes la sincro lo pasaba a 001-001 y los dos
        locales numeraban lo mismo (409 fiscal_number_conflict)."""
        from facturacion_electronica.models import FacturacionElectronicaConfig
        from facturacion_electronica.services.proveedores.fachada import sincronizar_emisor

        config = self._activar_api()
        config.establecimiento = '002'
        db.session.commit()

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   lambda *a, **k: (self._perfil(), None)):
            resumen, _error = sincronizar_emisor(config)

        config = FacturacionElectronicaConfig.obtener()
        self.assertEqual((config.establecimiento, config.punto_expedicion), ('002', '001'))
        self.assertIn('002-001', resumen)
        self.assertIn('Timbrado en la API', resumen)


if __name__ == '__main__':
    unittest.main()
