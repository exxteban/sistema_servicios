"""Inutilización del número quemado en modo API.

Hasta ahora el evento era del motor propio y en modo API no existía: el botón
estaba colgado de `herramientas_propias`, así que un cliente con la API quedaba
sin forma de justificar el hueco del timbrado ante la DNIT. Su API sí lo expone
(`POST /sifen/inutilizations/`).

Lo que se prueba acá es sobre todo cuándo **no** hay que informarlo: el número
quemado no se recupera nunca, así que equivocarse hacia ese lado es caro.
"""
import unittest
from unittest.mock import patch

from app import db
from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_ERROR,
    ESTADO_INUTILIZADO,
    ESTADO_RECHAZADO,
)

from test_facturacion_electronica_proveedor_base import BaseProveedorApi, respuesta_api


def evento_inutilizacion(**resultado):
    """`SifenEventRead` tal como responde el 201 del evento."""
    return {
        'id': 'e0e0e0e0-0000-4000-8000-000000000001',
        'event_type': 'inutilization',
        'event_type_display': 'Inutilización',
        'result': resultado or {'dCodRes': '0601', 'dMsgRes': 'Inutilización autorizada'},
    }


class TestProveedorApiInutilizacion(BaseProveedorApi):
    def _documento_quemado(self, estado=ESTADO_ERROR):
        """Número reservado cuyo DE nunca llegó a darse de alta en la API."""
        from facturacion_electronica.models import DocumentoElectronico

        venta = self._venta()
        documento = DocumentoElectronico(
            id_venta=venta.id_venta,
            tipo_documento=1,
            establecimiento='001',
            punto='001',
            numero='0000001',
            timbrado='12345678',
            estado=estado,
            respuesta_mensaje='Se cortó la luz antes de dar de alta el documento.',
        )
        db.session.add(documento)
        db.session.commit()
        return documento

    def test_informa_un_solo_numero_y_lo_deja_inutilizado(self):
        """El rango es de uno: los huecos no son contiguos salvo casualidad, y
        un rango que abarque un número emitido al medio lo quemaría también."""
        from facturacion_electronica.services.proveedores.fachada import inutilizar_documento

        self._activar_api()
        documento = self._documento_quemado()
        cuerpos = []

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta == '/sifen/inutilizations/':
                cuerpos.append(kwargs.get('json'))
                return evento_inutilizacion(), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = inutilizar_documento(documento, 'Corte de energía antes de emitir')

        self.assertIsNone(error)
        self.assertEqual(documento.estado, ESTADO_INUTILIZADO)
        self.assertIsNotNone(documento.fecha_cancelado)
        self.assertEqual(documento.motivo_cancelacion, 'Corte de energía antes de emitir')
        cuerpo = cuerpos[0]
        self.assertEqual(cuerpo['range_from'], 1)
        self.assertEqual(cuerpo['range_to'], 1)
        self.assertEqual(cuerpo['stamp_number'], '12345678')
        self.assertEqual(cuerpo['establishment'], '001')
        self.assertEqual(cuerpo['expedition_point'], '001')
        self.assertEqual(cuerpo['document_type'], 1)

    def test_no_quema_un_numero_que_la_api_todavia_puede_transmitir(self):
        """El caso que sólo existe en modo API: el DE ya está del otro lado y
        su pipeline lo lotea cada 30s. Inutilizar acá quema un número que iba
        a salir bien tres minutos después."""
        from facturacion_electronica.services.proveedores.api_inutilizacion import (
            MENSAJE_REMOTO_VIVO,
        )
        from facturacion_electronica.services.proveedores.fachada import inutilizar_documento

        self._activar_api()
        documento = self._documento_en_lote(1)
        rutas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            rutas.append(ruta)
            if ruta.startswith('/sifen/electronic-documents/'):
                return respuesta_api(estado='PENDING_BATCH'), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = inutilizar_documento(documento, 'Ya no la vamos a usar')

        self.assertEqual(error, MENSAJE_REMOTO_VIVO)
        self.assertNotEqual(documento.estado, ESTADO_INUTILIZADO)
        self.assertNotIn('/sifen/inutilizations/', rutas)

    def test_sin_confirmar_el_estado_remoto_no_se_decide(self):
        """Un timeout de su lado no dice nada sobre el documento, y quemar el
        número a ciegas no se deshace."""
        from facturacion_electronica.services.proveedores.fachada import inutilizar_documento

        self._activar_api()
        documento = self._documento_en_lote(1)
        rutas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            rutas.append(ruta)
            if ruta.startswith('/sifen/electronic-documents/'):
                return None, 'La API tardó demasiado en responder.'
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            _documento, error = inutilizar_documento(documento, 'Ya no la vamos a usar')

        self.assertIn('No se pudo confirmar', error)
        self.assertNotIn('/sifen/inutilizations/', rutas)

    def test_el_numero_rechazado_por_sifen_si_se_puede_inutilizar(self):
        """SIFEN lo vio y no lo aceptó: no hay un DE válido con ese número, así
        que el hueco es real y hay que informarlo."""
        from facturacion_electronica.services.proveedores.fachada import inutilizar_documento

        self._activar_api()
        documento = self._documento_en_lote(1)
        documento.timbrado = '12345678'
        db.session.commit()

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta.startswith('/sifen/electronic-documents/'):
                return respuesta_api(estado='REJECTED'), None
            if ruta == '/sifen/inutilizations/':
                return evento_inutilizacion(), None
            # Rastro del motivo del rechazo: no hay lote ni eventos en esta prueba.
            return {'results': []}, None

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = inutilizar_documento(documento, 'SIFEN rechazó el documento')

        self.assertIsNone(error)
        self.assertEqual(documento.estado, ESTADO_INUTILIZADO)

    def test_en_sandbox_no_se_informa_nada(self):
        """La API firma y valida el evento pero no lo transmite: decir que el
        hueco quedó justificado sería mentira."""
        from facturacion_electronica.services.proveedores.fachada import inutilizar_documento

        self._activar_api()
        documento = self._documento_quemado()
        perfil = self._perfil()
        perfil['sifen_mode'] = 'sandbox'
        rutas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            rutas.append(ruta)
            if ruta == '/sifen/me/':
                return perfil, None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = inutilizar_documento(documento, 'Corte de energía antes de emitir')

        self.assertIn('sandbox', error)
        self.assertNotEqual(documento.estado, ESTADO_INUTILIZADO)
        self.assertNotIn('/sifen/inutilizations/', rutas)

    def test_un_documento_aprobado_no_se_inutiliza(self):
        """Su número está usado: lo que corresponde es cancelarlo o acreditarlo."""
        from facturacion_electronica.services.proveedores.fachada import inutilizar_documento

        self._activar_api()
        documento = self._documento_quemado(estado=ESTADO_APROBADO)

        def _solicitar(config, metodo, ruta, **kwargs):
            raise AssertionError('no se debe llamar a la API por un documento aprobado')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            _documento, error = inutilizar_documento(documento, 'Me equivoqué de venta')

        self.assertIn('ya salió hacia SIFEN', error)

    def test_el_rechazo_del_evento_no_deja_el_numero_por_inutilizado(self):
        """El `result` es un objeto libre en su OpenAPI: si dice que SIFEN no
        lo autorizó, el hueco sigue abierto y la pantalla lo tiene que decir."""
        from facturacion_electronica.services.proveedores.fachada import inutilizar_documento

        self._activar_api()
        documento = self._documento_quemado()

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta == '/sifen/inutilizations/':
                return evento_inutilizacion(
                    dCodRes='0160', dMsgRes='Rango de numeración rechazado',
                ), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = inutilizar_documento(documento, 'Corte de energía antes de emitir')

        self.assertIn('0160', error)
        self.assertNotEqual(documento.estado, ESTADO_INUTILIZADO)
        self.assertIsNone(documento.fecha_cancelado)

    def test_la_pantalla_ofrece_el_boton_en_modo_api(self):
        """La capacidad es propia y no `herramientas_propias`: con la API
        activa el botón tiene que existir, que es lo que faltaba."""
        from facturacion_electronica.services.acciones import acciones_para_venta
        from facturacion_electronica.services.proveedores.fachada import capacidades

        self._activar_api()
        documento = self._documento_quemado(estado=ESTADO_RECHAZADO)

        self.assertTrue(capacidades()['inutilizacion'])
        acciones = acciones_para_venta(documento.venta, puede_operar=True)
        self.assertTrue(acciones['puede_inutilizar'])


if __name__ == '__main__':
    unittest.main()
