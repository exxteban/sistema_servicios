"""Lo que trajeron las versiones 1.3 a 1.7.1 de la API de FE.

- El receptor: nombre de 4 caracteres y DV del RUC validados antes de
  reservar número (la API los rechaza con 400 desde 1.3.0/1.4.0).
- El envelope de error `{"error": {...}}` legible en pantalla.
- `sifen_result` (1.6.0): el motivo del rechazo sin ir a buscar lotes.
- `correct/` (1.7.0): reintentar una factura rechazada la corrige y la
  reenvía con el mismo número, en vez de quedarse refrescando un REJECTED.

Comparte el andamiaje de `test_facturacion_electronica_proveedor_base.py`.
"""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import db
from facturacion_electronica import ESTADO_FIRMADO, ESTADO_RECHAZADO

from test_facturacion_electronica_proveedor_base import BaseProveedorApi, respuesta_api

SOLICITAR = 'facturacion_electronica.services.proveedores.api_client.solicitar'


def _cliente(**datos):
    base = {'id_cliente': 7, 'email': None, 'direccion': None, 'telefono': None}
    base.update(datos)
    return SimpleNamespace(**base)


# -- reglas del receptor, sin base ------------------------------------------

def test_digito_verificador_modulo_11():
    from facturacion_electronica.services.validacion import digito_verificador_ruc

    # Casos del algoritmo de la SET (mismos que valida la API).
    assert digito_verificador_ruc('80012345') == 0
    assert digito_verificador_ruc('80000000') == 5


def test_dv_equivocado_frena_con_el_dv_correcto_en_el_mensaje():
    from facturacion_electronica.services.validacion import validar_receptor_api

    error = validar_receptor_api(_cliente(ruc_ci='80012345-6', nombre='Ferretería SA'))
    assert error and 'dígito verificador' in error and 'es 0' in error
    assert validar_receptor_api(_cliente(ruc_ci='80012345-0', nombre='Ferretería SA')) is None


def test_nombre_corto_frena_solo_si_el_receptor_esta_identificado():
    from facturacion_electronica.services.proveedores.api_payload import construir_receptor
    from facturacion_electronica.services.validacion import validar_receptor_api

    assert 'menos de 4' in validar_receptor_api(_cliente(ruc_ci='4281292', nombre='Ana'))

    # Sin documento viaja innominado: no se la frena, va el literal de SIFEN.
    anonima = _cliente(ruc_ci='', nombre='Ana')
    assert validar_receptor_api(anonima) is None
    assert construir_receptor(anonima)['name'] == 'Sin Nombre'


# -- envelope de error ------------------------------------------------------

def _respuesta(cuerpo):
    return SimpleNamespace(status_code=400, text=json.dumps(cuerpo), json=lambda: cuerpo)


def test_envelope_de_error_se_lee_con_sus_campos():
    from facturacion_electronica.services.proveedores.api_client import _detalle_error

    texto = _detalle_error(_respuesta({'error': {
        'code': 'validation_error',
        'detail': 'El DV no corresponde.',
        'extra': {'issues': [
            {'field': 'receiver.dv', 'detail': 'El DV no corresponde.'},
            {'field': 'receiver.name', 'detail': 'Mínimo 4 caracteres.'},
        ]},
    }}))
    assert 'receiver.dv: El DV no corresponde.' in texto
    assert 'receiver.name: Mínimo 4 caracteres.' in texto
    assert texto.endswith('(validation_error)')
    assert "{'code'" not in texto

    simple = _detalle_error(_respuesta({'error': {'code': 'invalid_payment', 'detail': 'No suma.'}}))
    assert simple == 'No suma. (invalid_payment)'


# -- con base -----------------------------------------------------------------

class TestCorreccionApi(BaseProveedorApi):
    def _cliente_con_dv_equivocado(self):
        from app.models import Cliente

        cliente = Cliente(nombre='Ferretería SA', ruc_ci='80012345-6')
        db.session.add(cliente)
        db.session.commit()
        self.cliente = cliente
        return cliente

    def test_dv_equivocado_no_consume_numero_ni_llama_al_alta(self):
        from facturacion_electronica.services.numeracion_service import peek_proximo_numero
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        self._cliente_con_dv_equivocado()
        proximo = peek_proximo_numero('001', '001')

        def _solicitar(config, metodo, ruta, **kwargs):
            raise AssertionError(f'no se debe llamar a la API: {ruta}')

        with patch(SOLICITAR, _solicitar):
            documento, error = emitir_para_pos(self._venta())

        self.assertIn('dígito verificador', error)
        self.assertIsNone(documento.numero)
        self.assertEqual(peek_proximo_numero('001', '001'), proximo)

    def test_el_motivo_sale_de_sifen_result_sin_buscar_lotes(self):
        from facturacion_electronica.services.proveedores.api import ProveedorApi

        self._activar_api()
        documento = self._documento_en_lote(1)
        rutas = []
        resultado = {
            'status': 'Rechazado', 'codes': '0160,1311',
            'messages': [
                {'code': '0160', 'message': 'XML malformado'},
                {'code': '1311', 'message': 'DV del receptor inválido'},
            ],
            'batch_id': 'b0c0ffee-0000-4000-8000-00000000000a', 'protocol': None,
        }

        def _solicitar(config, metodo, ruta, **kwargs):
            rutas.append(ruta)
            if ruta.startswith('/sifen/electronic-documents/'):
                return respuesta_api(estado='REJECTED', sifen_result=resultado), None
            raise AssertionError(f'no hace falta ir a buscar el lote: {ruta}')

        with patch(SOLICITAR, _solicitar):
            ProveedorApi().avanzar(documento)

        self.assertEqual(documento.estado, ESTADO_RECHAZADO)
        self.assertIn('0160 - XML malformado', documento.respuesta_mensaje)
        self.assertIn('1311 - DV del receptor inválido', documento.respuesta_mensaje)
        self.assertEqual(documento.api_lote_id, resultado['batch_id'])
        self.assertEqual(len(rutas), 1)

    def _rechazada(self):
        """Factura dada de alta y rechazada, con la venta de la base."""
        documento = self._documento_en_lote(1)
        documento.estado = ESTADO_RECHAZADO
        documento.respuesta_codigo = 'REJECTED'
        documento.api_idempotency_key = 'fe-1-001-001-0000001-1'
        documento.api_lote_id = 'lote-del-rechazo'
        db.session.commit()
        return documento

    def test_reintentar_una_rechazada_la_corrige_con_el_mismo_numero(self):
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        documento = self._rechazada()
        llamadas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            llamadas.append((metodo, ruta, kwargs.get('json'), kwargs.get('headers')))
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta.endswith('/correct/'):
                return respuesta_api(estado='PENDING_BATCH'), None
            raise AssertionError(f'ruta inesperada: {metodo} {ruta}')

        with patch(SOLICITAR, _solicitar):
            documento, error = emitir_para_pos(documento.venta)

        self.assertIsNone(error)
        self.assertEqual(documento.estado, ESTADO_FIRMADO)
        self.assertEqual(documento.numero, '0000001')
        self.assertIsNone(documento.api_lote_id)
        correcciones = [c for c in llamadas if c[1].endswith('/correct/')]
        self.assertEqual(len(correcciones), 1)
        _metodo, ruta, cuerpo, headers = correcciones[0]
        self.assertEqual(ruta, f'/sifen/electronic-documents/{documento.api_documento_id}/correct/')
        self.assertEqual(cuerpo['document_number'], '0000001')
        # Clave distinta de la emisión, como exige la API.
        self.assertNotEqual(headers['Idempotency-Key'], 'fe-1-001-001-0000001-1')
        self.assertTrue(headers['Idempotency-Key'].startswith('fe-1-001-001-0000001-1-corr-'))
        self.assertFalse(any(c[1] == '/sifen/electronic-documents/' for c in llamadas))

    def test_la_clave_se_repite_al_reintentar_y_cambia_ante_otro_rechazo(self):
        from facturacion_electronica.services.proveedores.api_correccion import clave_correccion

        self._activar_api()
        documento = self._rechazada()
        cuerpo = {'document_number': '0000001', 'lines': []}

        primera = clave_correccion(documento, cuerpo)
        self.assertEqual(clave_correccion(documento, cuerpo), primera)
        self.assertLessEqual(len(primera), 100)

        documento.respuesta_raw = json.dumps({'sifen_result': {'batch_id': 'otro-lote'}})
        self.assertNotEqual(clave_correccion(documento, cuerpo), primera)

    def test_si_la_correccion_falla_sigue_rechazada(self):
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        self._activar_api()
        documento = self._rechazada()

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta.endswith('/correct/'):
                return None, 'La API respondió 400: issued_at (cdc_fields_changed)'
            raise AssertionError(f'ruta inesperada: {metodo} {ruta}')

        with patch(SOLICITAR, _solicitar):
            documento, error = emitir_para_pos(documento.venta)

        self.assertIn('cdc_fields_changed', error)
        self.assertEqual(documento.estado, ESTADO_RECHAZADO)
        self.assertIn('No se pudo corregir', documento.respuesta_mensaje)

    def test_una_nota_de_credito_rechazada_no_se_corrige(self):
        """`correct/` es sólo para facturas: la NC rechazada se relee y nada más."""
        from facturacion_electronica import TIPO_NOTA_CREDITO
        from facturacion_electronica.services.proveedores.api import ProveedorApi

        self._activar_api()
        documento = self._rechazada()
        documento.tipo_documento = TIPO_NOTA_CREDITO
        db.session.commit()
        rutas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            rutas.append(ruta)
            if ruta.startswith('/sifen/electronic-documents/'):
                return respuesta_api(estado='REJECTED'), None
            return {'results': []}, None

        with patch(SOLICITAR, _solicitar):
            ProveedorApi()._alta_remota(None, documento, documento.venta)

        self.assertFalse(any(r.endswith('/correct/') for r in rutas))

    # -- pantalla: corregir en vez de inutilizar --------------------------------

    def test_rechazada_a_tiempo_ofrece_corregir_y_no_inutilizar(self):
        from facturacion_electronica.services.acciones import acciones_para_venta

        self._activar_api()
        documento = self._rechazada()

        acciones = acciones_para_venta(documento.venta, puede_operar=True)

        self.assertTrue(acciones['puede_corregir_rechazo'])
        self.assertFalse(acciones['puede_inutilizar'])
        # El job no la toca: decir "se reintenta solo" sería mentir.
        self.assertFalse(acciones['envio_en_curso'])

    def test_rechazada_fuera_de_plazo_ofrece_inutilizar(self):
        from datetime import datetime, timedelta

        from facturacion_electronica.services.acciones import acciones_para_venta

        self._activar_api()
        documento = self._rechazada()
        documento.venta.fecha_venta = datetime.utcnow() - timedelta(days=31)
        db.session.commit()

        acciones = acciones_para_venta(documento.venta, puede_operar=True)

        self.assertFalse(acciones['puede_corregir_rechazo'])
        self.assertTrue(acciones['puede_inutilizar'])

    # -- job: el 0160 del schema se reenvía solo ---------------------------------

    def _job(self, rutas):
        from facturacion_electronica.services.envio_automatico import procesar_pendientes

        def _solicitar(config, metodo, ruta, **kwargs):
            rutas.append((metodo, ruta))
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta.endswith('/correct/'):
                return respuesta_api(estado='PENDING_BATCH'), None
            raise AssertionError(f'ruta inesperada: {metodo} {ruta}')

        with patch(SOLICITAR, _solicitar):
            return procesar_pendientes()

    def test_el_job_reenvia_el_rechazo_por_schema(self):
        self._activar_api()
        documento = self._rechazada()
        documento.respuesta_mensaje = (
            'Rechazado por SIFEN: 0160 - XML malformado: No se informó el schema en el XML'
        )
        db.session.commit()
        rutas = []

        resumen = self._job(rutas)

        self.assertEqual(resumen['ok'], 1)
        self.assertIn(('POST', f'/sifen/electronic-documents/{documento.api_documento_id}/correct/'),
                      rutas)
        self.assertEqual(documento.estado, ESTADO_FIRMADO)

    def test_el_job_no_toca_otros_rechazos(self):
        self._activar_api()
        documento = self._rechazada()
        documento.respuesta_mensaje = 'Rechazado por SIFEN: 1311 - DV del receptor inválido'
        db.session.commit()
        rutas = []

        resumen = self._job(rutas)

        self.assertEqual(resumen['procesados'], 0)
        self.assertEqual(rutas, [])
        self.assertEqual(documento.estado, ESTADO_RECHAZADO)

    def test_el_job_no_reenvia_fuera_de_plazo_y_no_vuelve_a_intentar(self):
        from datetime import datetime, timedelta

        self._activar_api()
        documento = self._rechazada()
        documento.respuesta_mensaje = 'Rechazado por SIFEN: 0160 - No se informó el schema'
        documento.venta.fecha_venta = datetime.utcnow() - timedelta(days=31)
        db.session.commit()
        rutas = []

        primera = self._job(rutas)

        self.assertEqual(primera['error'], 1)
        self.assertEqual(rutas, [])
        self.assertIn('720h', documento.respuesta_mensaje)
        # El mensaje cambió: ya no entra al filtro en la pasada siguiente.
        documento.reintentar_despues = None
        db.session.commit()
        self.assertEqual(self._job(rutas)['procesados'], 0)

    def _logueado_con_fe(self):
        from app.models import Configuracion, Usuario
        from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'true')
        db.session.commit()
        admin = Usuario.query.filter_by(username='admin').first()
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion['_user_id'] = str(admin.id_usuario)
            sesion['_fresh'] = True
        return cliente

    def test_el_detalle_de_la_venta_dibuja_corregir_con_el_motivo(self):
        self._activar_api()
        documento = self._rechazada()
        documento.respuesta_mensaje = 'Rechazado por SIFEN: 1311 - DV del receptor inválido'
        db.session.commit()

        respuesta = self._logueado_con_fe().get(f'/ventas/{documento.id_venta}')
        html = respuesta.get_data(as_text=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('Corregir y reenviar', html)
        self.assertIn('1311 - DV del receptor inválido', html)
        self.assertIn(f'/emitir-completo/{documento.id_venta}', html)
        self.assertNotIn('Inutilizar número', html)

    def test_el_modal_del_historial_trae_corregir_y_el_motivo(self):
        self._activar_api()
        documento = self._rechazada()
        documento.respuesta_mensaje = 'Rechazado por SIFEN: 1311 - DV del receptor inválido'
        db.session.commit()

        respuesta = self._logueado_con_fe().get(f'/reportes/ventas/{documento.id_venta}/detalle')
        fe = respuesta.get_json()['fe']

        self.assertTrue(fe['puede_corregir_rechazo'])
        self.assertFalse(fe['puede_inutilizar'])
        self.assertIn('1311', fe['motivo_rechazo'])

    # -- número fiscal tomado por otro documento (409 fiscal_number_conflict) ----

    def _conflicto(self, listado):
        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        rutas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            rutas.append((metodo, ruta))
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if metodo == 'POST' and ruta == '/sifen/electronic-documents/':
                return None, ("La API respondió 409: Ya existe un documento electrónico con el "
                              "número fiscal ... (fiscal_number_conflict)")
            if metodo == 'GET' and ruta.startswith('/sifen/electronic-documents/?'):
                return {'results': listado}, None
            if ruta.startswith('/sifen/electronic-documents/by-cdc/'):
                return {'qr_url': 'https://qr'}, None
            raise AssertionError(f'ruta inesperada: {metodo} {ruta}')

        with patch(SOLICITAR, _solicitar):
            return emitir_para_pos(self._venta())

    def test_el_numero_de_otro_documento_se_suelta_para_tomar_el_siguiente(self):
        self._activar_api()

        from facturacion_electronica.services.proveedores.fachada import emitir_para_pos

        documento, error = self._conflicto(listado=[])

        self.assertIn('0000001 ya lo tiene otro documento', error)
        self.assertIsNone(documento.numero)
        self.assertIsNone(documento.api_idempotency_key)

        altas = []

        def _solicitar(config, metodo, ruta, json=None, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            altas.append(json)
            return respuesta_api(), None

        with patch(SOLICITAR, _solicitar):
            documento, error = emitir_para_pos(documento.venta)

        self.assertIsNone(error)
        self.assertEqual(altas[0]['document_number'], '0000002')

    def test_si_el_numero_es_de_esta_venta_se_adopta(self):
        """Lo dio de alta el proveedor con otra clave: mismo external_ref y el
        mismo número en el CDC. Es este documento, no hay que renumerar."""
        self._activar_api()
        cdc = '01' + '80178105' + '1' + '001' + '001' + '0000001' + '1' + '20260925' + '1' + '123456789' + '0'
        self.assertEqual(len(cdc), 44)
        remoto = respuesta_api(estado='PENDING_BATCH', cdc=cdc, idempotency_key='otra-clave')

        documento, error = self._conflicto(listado=[remoto])

        self.assertIsNone(error)
        self.assertEqual(documento.numero, '0000001')
        self.assertEqual(documento.api_documento_id, remoto['id'])
        self.assertEqual(documento.estado, ESTADO_FIRMADO)

    def test_la_vista_previa_no_ofrece_inutilizar_lo_que_todavia_sale(self):
        """Venta #115 del demo: firmada, esperando el lote, y la vista previa
        ofrecía quemar su número. Usa la misma regla que la pantalla de la venta."""
        from datetime import datetime, timedelta

        from flask import url_for

        self._activar_api()
        documento = self._documento_en_lote(1)
        cliente = self._logueado_con_fe()
        with self.app.test_request_context():
            url = url_for('facturacion_electronica.vista_previa', venta=documento.id_venta)

        self.assertNotIn('Inutilizar número', cliente.get(url).get_data(as_text=True))

        documento.estado = ESTADO_RECHAZADO
        documento.venta.fecha_venta = datetime.utcnow() - timedelta(days=31)
        db.session.commit()
        self.assertIn('Inutilizar número', cliente.get(url).get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
