"""NC de anulación ("Anular con NC") en modo API.

El botón existía sólo para el motor propio: `ProveedorApi` no implementaba
`emitir_nota_credito_correccion`, así que heredaba el "no disponible" del
contrato. Hoy no se nota porque la API rechaza toda NC en el borde y el botón
está oculto, pero el día que la habiliten el botón aparecía y no funcionaba.

Se corre con `API_EMITE_NOTAS_CREDITO` en True, como el resto de las pruebas
de NC: lo que se prueba es el circuito, no el bloqueo del proveedor (eso tiene
su propia prueba abajo).
"""
import unittest
from unittest.mock import patch

from app import db
from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_ERROR,
    ESTADO_RECHAZADO,
    TIPO_FACTURA,
    TIPO_NOTA_CREDITO,
)

from test_facturacion_electronica_proveedor_base import (
    BaseProveedorApi,
    respuesta_api,
    simular_xml_de_factura,
    xml_factura,
)

NC_HABILITADA = 'facturacion_electronica.services.proveedores.api.API_EMITE_NOTAS_CREDITO'


class TestProveedorApiAnulacionConNc(BaseProveedorApi):
    def setUp(self):
        super().setUp()
        self._usar_cliente_identificado()
        habilitada = patch(NC_HABILITADA, True)
        habilitada.start()
        self.addCleanup(habilitada.stop)
        self.xml_de_factura = simular_xml_de_factura(self)

    def _perfil_con_timbrado_de_nc(self):
        perfil = self._perfil()
        perfil['stamps'].append({
            'id': 'aaaaaaaa-0000-4000-8000-000000000005',
            'number': '12345678',
            'establishment': '001',
            'expedition_point': '001',
            'document_type': TIPO_NOTA_CREDITO,
            'valid_from': '2026-01-01',
        })
        return perfil

    def _venta_facturada(self, precio=100000):
        """Venta con un ítem y su factura ya aprobada por SIFEN."""
        from app.models import Categoria, Producto
        from app.models.venta import DetalleVenta
        from facturacion_electronica.models import DocumentoElectronico

        categoria = Categoria.query.first()
        producto = Producto(
            codigo='ANC-001', nombre='Producto anulación',
            id_categoria=categoria.id_categoria, precio_compra=5000,
            precio_venta=precio, stock_actual=10,
        )
        db.session.add(producto)
        db.session.flush()

        venta = self._venta()
        venta.estado = 'completada'
        db.session.add(DetalleVenta(
            id_venta=venta.id_venta, id_producto=producto.id_producto, cantidad=1,
            precio_unitario=precio, precio_original=precio, porcentaje_iva=10,
            monto_iva=0, descuento_linea=0, subtotal=precio,
        ))
        factura = DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA, numero='0000001',
            establecimiento='001', punto='001', timbrado='12345678',
            estado=ESTADO_APROBADO, respuesta_codigo='APPROVED', cdc='0' * 44,
            api_documento_id='d0c0ffee-0000-4000-8000-000000000001',
        )
        db.session.add(factura)
        db.session.commit()
        return venta, factura

    def test_acredita_la_factura_entera_contra_el_cdc_original(self):
        """Sin devolución detrás las líneas son las de la venta, y `associated`
        es lo que ata la NC a la factura que corrige."""
        from facturacion_electronica.services.proveedores.fachada import (
            emitir_nota_credito_correccion,
        )

        self._activar_api()
        venta, factura = self._venta_facturada()
        altas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil_con_timbrado_de_nc(), None
            if ruta == '/sifen/electronic-documents/':
                altas.append(kwargs.get('json'))
                return respuesta_api(document_type=TIPO_NOTA_CREDITO), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = emitir_nota_credito_correccion(venta, 1, 'Cliente equivocado')

        self.assertIsNone(error)
        self.assertEqual(documento.tipo_documento, TIPO_NOTA_CREDITO)
        self.assertIsNone(documento.id_devolucion)
        self.assertEqual(documento.id_documento_asociado, factura.id)
        cuerpo = altas[0]
        self.assertEqual(cuerpo['document_type'], TIPO_NOTA_CREDITO)
        self.assertEqual(cuerpo['associated']['cdc'], '0' * 44)
        self.assertEqual(len(cuerpo['lines']), 1)
        self.assertEqual(cuerpo['external_ref'], f'anulacion-{venta.id_venta}')

    def test_la_nc_de_anulacion_lleva_su_propio_correlativo(self):
        """Comparte el rango con las demás NC, no con la factura: el timbrado
        de tipo 5 es otro."""
        from facturacion_electronica.services.proveedores.fachada import (
            emitir_nota_credito_correccion,
        )

        self._activar_api()
        venta, factura = self._venta_facturada()

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil_con_timbrado_de_nc(), None
            if ruta == '/sifen/electronic-documents/':
                return respuesta_api(document_type=TIPO_NOTA_CREDITO), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            documento, error = emitir_nota_credito_correccion(venta, 1)

        self.assertIsNone(error)
        self.assertEqual(documento.numero, '0000001')
        self.assertNotEqual(documento.id, factura.id)

    def test_no_se_emite_una_segunda_nc_de_anulacion(self):
        """La factura ya quedó sin efecto: otra NC acreditaría dos veces."""
        from facturacion_electronica.services.proveedores.fachada import (
            emitir_nota_credito_correccion,
        )

        self._activar_api()
        venta, _factura = self._venta_facturada()

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil_con_timbrado_de_nc(), None
            if ruta == '/sifen/electronic-documents/':
                return respuesta_api(document_type=TIPO_NOTA_CREDITO), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            _primera, error = emitir_nota_credito_correccion(venta, 1)
            self.assertIsNone(error)
            _segunda, error = emitir_nota_credito_correccion(venta, 1)

        self.assertIn('ya tiene una nota de crédito de anulación', error)

    def test_factura_innominada_no_se_acredita_aunque_la_ficha_tenga_cedula(self):
        """La NC lleva el receptor de la factura, no el de la ficha: si la
        factura salió innominada, cargar la cédula después no la salva. Se
        frena antes de reservar número y sin dar de alta nada."""
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.proveedores.fachada import (
            emitir_nota_credito_correccion,
        )

        self._activar_api()
        venta, _factura = self._venta_facturada()
        innominada = xml_factura('0', 'Sin Nombre').replace(
            '<iTipIDRec>1</iTipIDRec>', '<iTipIDRec>5</iTipIDRec>')
        self.xml_de_factura.return_value = (innominada, None)

        with patch(
            'facturacion_electronica.services.proveedores.api_client.solicitar'
        ) as nunca:
            documento, error = emitir_nota_credito_correccion(venta, 1)

        nunca.assert_not_called()
        self.assertIsNone(documento)
        self.assertIn('receptor sin identificar', error)
        self.assertIn('completar ahora la ficha', error)
        self.assertEqual(DocumentoElectronico.query.filter_by(
            id_venta=venta.id_venta, tipo_documento=TIPO_NOTA_CREDITO).count(), 0)

    def test_la_nc_que_reemplaza_a_una_cancelada_estrena_referencia(self):
        """La API reserva `external_ref` también para los cancelados: repetir
        `anulacion-<venta>` era `409 external_ref_conflict`."""
        from facturacion_electronica import ESTADO_CANCELADO
        from facturacion_electronica.services.proveedores.fachada import (
            emitir_nota_credito_correccion,
        )

        self._activar_api()
        venta, _factura = self._venta_facturada()
        altas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil_con_timbrado_de_nc(), None
            if ruta == '/sifen/electronic-documents/':
                altas.append(kwargs.get('json'))
                return respuesta_api(document_type=TIPO_NOTA_CREDITO), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            primera, error = emitir_nota_credito_correccion(venta, 1)
            self.assertIsNone(error)
            primera.estado = ESTADO_CANCELADO
            db.session.commit()
            segunda, error = emitir_nota_credito_correccion(venta, 1)

        self.assertIsNone(error)
        self.assertNotEqual(segunda.id, primera.id)
        self.assertEqual(altas[0]['external_ref'], f'anulacion-{venta.id_venta}')
        self.assertEqual(altas[1]['external_ref'], f'anulacion-{venta.id_venta}-2')

    def test_el_job_reintenta_la_nc_de_anulacion(self):
        """`_reintentar_nota_credito` daba por sentado que toda NC tiene una
        devolución: la de anulación quedaba huérfana ('la devolución ya no
        existe') y el job la reintentaba para siempre sin llegar a emitirla."""
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.proveedores.api import ProveedorApi

        self._activar_api()
        venta, factura = self._venta_facturada()
        nota = DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=TIPO_NOTA_CREDITO,
            id_documento_asociado=factura.id, nc_motivo=1, nc_motivo_desc='Devolución',
            establecimiento='001', punto='001', numero='0000001', estado=ESTADO_ERROR,
        )
        db.session.add(nota)
        db.session.commit()
        altas = []

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil_con_timbrado_de_nc(), None
            if ruta == '/sifen/electronic-documents/':
                altas.append(kwargs.get('json'))
                return respuesta_api(document_type=TIPO_NOTA_CREDITO), None
            raise AssertionError(f'ruta inesperada: {ruta}')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            error = ProveedorApi().avanzar(nota)

        self.assertIsNone(error)
        self.assertEqual(len(altas), 1)
        self.assertEqual(altas[0]['document_type'], TIPO_NOTA_CREDITO)

    def _api_que_captura(self, altas, claves=None):
        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil_con_timbrado_de_nc(), None
            if ruta == '/sifen/electronic-documents/':
                altas.append(kwargs.get('json'))
                if claves is not None:
                    claves.append((kwargs.get('headers') or {}).get('Idempotency-Key'))
                return respuesta_api(document_type=TIPO_NOTA_CREDITO), None
            if metodo == 'GET':
                return respuesta_api(document_type=TIPO_NOTA_CREDITO), None
            raise AssertionError(f'ruta inesperada: {ruta}')
        return _solicitar

    def test_acredita_lo_facturado_con_el_descuento_global(self):
        """Venta #123 de Janelipy: 5% de descuento sobre el total. La factura
        lo repartió en los precios y la NC acreditaba a precio lleno
        (613.076 contra 645.343)."""
        from facturacion_electronica.services.proveedores.fachada import (
            emitir_nota_credito_correccion,
        )

        self._activar_api()
        venta, _factura = self._venta_facturada(precio=100000)
        venta.total = 95000
        db.session.commit()
        altas = []

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   self._api_que_captura(altas)):
            _documento, error = emitir_nota_credito_correccion(venta, 1)

        self.assertIsNone(error)
        acreditado = sum(float(l['unit_price']) * float(l['quantity']) for l in altas[0]['lines'])
        self.assertAlmostEqual(acreditado, 95000, places=2)

    def test_el_receptor_es_el_de_la_factura_no_el_de_la_ficha(self):
        """La factura salió a una cédula; después la ficha pasó a tener RUC.
        La NC tiene que hablar del mismo comprador que la factura."""
        from facturacion_electronica.services.proveedores.fachada import (
            emitir_nota_credito_correccion,
        )

        self._activar_api()
        venta, _factura = self._venta_facturada()
        self.cliente.ruc_ci = '4281292-5'
        db.session.commit()
        self.xml_de_factura.return_value = (xml_factura('4281292', 'Esteban Lezcano'), None)
        altas = []

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   self._api_que_captura(altas)):
            _documento, error = emitir_nota_credito_correccion(venta, 1)

        self.assertIsNone(error)
        receptor = altas[0]['receiver']
        self.assertEqual(receptor['nature'], 2)
        self.assertEqual(receptor['id_number'], '4281292')
        self.assertEqual(receptor['name'], 'Esteban Lezcano')
        self.assertNotIn('ruc', receptor)

    def test_sin_el_xml_de_la_factura_no_se_emite(self):
        """Caer a la ficha es el error que se corrige: mejor frenar y reintentar.

        Se frena antes de crear la NC: un corte pasajero no consume número."""
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.proveedores.fachada import (
            emitir_nota_credito_correccion,
        )

        self._activar_api()
        venta, _factura = self._venta_facturada()
        self.xml_de_factura.return_value = (None, 'La API tardó demasiado en responder.')
        altas = []

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   self._api_que_captura(altas)):
            documento, error = emitir_nota_credito_correccion(venta, 1)

        self.assertIn('receptor de la factura', error)
        self.assertEqual(altas, [])
        self.assertIsNone(documento)
        self.assertEqual(DocumentoElectronico.query.filter_by(
            id_venta=venta.id_venta, tipo_documento=TIPO_NOTA_CREDITO).count(), 0)

    def test_una_nc_rechazada_se_vuelve_a_dar_de_alta_con_el_mismo_numero(self):
        """Antes el botón sólo refrescaba la NC rechazada y decía "emitida".
        El rechazo libera el número en la API: alta nueva, mismo número, clave nueva."""
        from facturacion_electronica.services.proveedores.fachada import (
            emitir_nota_credito_correccion,
        )

        self._activar_api()
        venta, _factura = self._venta_facturada()
        altas, claves = [], []

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   self._api_que_captura(altas, claves)):
            documento, error = emitir_nota_credito_correccion(venta, 1)
            self.assertIsNone(error)
            documento.estado = ESTADO_RECHAZADO
            documento.respuesta_codigo = 'REJECTED'
            db.session.commit()

            reemitida, error = emitir_nota_credito_correccion(venta, 1)

        self.assertIsNone(error)
        self.assertEqual(reemitida.id, documento.id)
        self.assertEqual(len(altas), 2)
        self.assertEqual(altas[0]['document_number'], altas[1]['document_number'])
        self.assertNotEqual(claves[0], claves[1])
        self.assertNotEqual(reemitida.estado, ESTADO_RECHAZADO)

    def test_con_la_nc_bloqueada_el_mensaje_explica_por_que(self):
        """Estado real de hoy. Antes caía en el 'no disponible' genérico del
        contrato, que no le dice nada a nadie."""
        from facturacion_electronica.services.proveedores.fachada import (
            emitir_nota_credito_correccion,
        )

        self._activar_api()
        venta, _factura = self._venta_facturada()

        with patch(NC_HABILITADA, False), patch(
            'facturacion_electronica.services.proveedores.api_client.solicitar'
        ) as nunca:
            _documento, error = emitir_nota_credito_correccion(venta, 1)

        nunca.assert_not_called()
        self.assertIn('notas de crédito', error)
        self.assertIn('no transmitió ninguna a SIFEN', error)


def test_external_ref_de_la_nc_de_anulacion_no_es_devolucion_none():
    """Sin esto todas las NC de anulación compartían la misma referencia, y la
    recuperación de un alta perdida buscaba por una que no era la del alta."""
    from types import SimpleNamespace

    from facturacion_electronica.services.proveedores.api_payload import referencia_externa

    anulacion = SimpleNamespace(tipo_documento=5, id_venta=42, id_devolucion=None)
    assert referencia_externa(anulacion) == 'anulacion-42'


if __name__ == '__main__':
    unittest.main()
