"""Nota de crédito por devolución, contra la API externa.

Los invariantes que se cuidan acá:

- la NC lleva **su propio correlativo**: factura 0000001 y NC 0000001 conviven;
- la NC **no** es la factura de la venta: `obtener_documento` la ignora, o el
  POS, el KuDE y la guarda de anulación pasarían a mirar el documento
  equivocado;
- se acredita lo que la **factura** dice, no lo que la devolución reembolsó,
  y la diferencia se avisa en vez de elegirla en silencio;
- una devolución no puede generar dos notas de crédito.
"""
import unittest
from datetime import datetime
from unittest.mock import patch

from app import create_app, db
from app.models import (
    Categoria,
    Cliente,
    DetalleVenta,
    Producto,
    SesionCaja,
    Usuario,
    Venta,
)
from app.models.devolucion import DetalleDevolucion, Devolucion
from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    TIPO_FACTURA,
    TIPO_NOTA_CREDITO,
)
from facturacion_electronica.models import DocumentoElectronico, FacturacionElectronicaConfig
from facturacion_electronica.services.proveedores import api_client

from test_facturacion_electronica_proveedor_base import simular_xml_de_factura


class TestNotaCredito(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        # El circuito de la NC está entero y es lo que estas pruebas cubren; lo
        # que falta es que el proveedor habilite `document_type` 5, que hoy
        # rechaza en el borde (api.API_EMITE_NOTAS_CREDITO). Acá se corre con la
        # llave puesta; el bloqueo tiene su propia prueba en el archivo del
        # proveedor.
        nc_habilitada = patch(
            'facturacion_electronica.services.proveedores.api.API_EMITE_NOTAS_CREDITO', True,
        )
        nc_habilitada.start()
        self.addCleanup(nc_habilitada.stop)
        simular_xml_de_factura(self)

        self.admin = Usuario.query.filter_by(username='admin').first()
        # Cliente **identificado**: SIFEN rechaza una nota de crédito cuyo
        # receptor es innominado ("El adquiriente ... no se encuentra
        # identificado"), así que el consumidor final no sirve para este caso.
        self.cliente = Cliente(nombre='Alfio Oviedo', ruc_ci='4281292')
        db.session.add(self.cliente)
        db.session.flush()
        self.sesion = SesionCaja(
            id_caja=1, id_usuario=self.admin.id_usuario, monto_inicial=0, estado='abierta',
        )
        db.session.add(self.sesion)

        categoria = Categoria.query.first()
        if categoria is None:
            categoria = Categoria(nombre='General')
            db.session.add(categoria)
            db.session.flush()
        self.producto = Producto(
            codigo='NC-001', nombre='Producto NC', id_categoria=categoria.id_categoria,
            precio_compra=5000, precio_venta=100000, stock_actual=10,
        )
        db.session.add(self.producto)
        db.session.commit()

        config = FacturacionElectronicaConfig.obtener()
        config.proveedor = 'api'
        config.api_url = 'https://api.ejemplo.test'
        config.api_client_id = 'cliente-test'
        config.api_credenciales = 'secreto'
        config.establecimiento = '001'
        config.punto_expedicion = '001'
        db.session.commit()

    def tearDown(self):
        from facturacion_electronica.services.proveedores.api import olvidar_perfil

        olvidar_perfil()
        api_client.olvidar_token()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # ------------------------------------------------------------ fixtures

    def _venta_facturada(self, precio=100000, descuento=0):
        venta = Venta(
            id_cliente=self.cliente.id_cliente,
            id_sesion_caja=self.sesion.id_sesion,
            subtotal=precio - descuento,
            total=precio - descuento,
            fecha_venta=datetime.utcnow(),
            estado='completada',
        )
        db.session.add(venta)
        db.session.flush()
        detalle = DetalleVenta(
            id_venta=venta.id_venta,
            id_producto=self.producto.id_producto,
            cantidad=1,
            precio_unitario=precio,
            precio_original=precio,
            porcentaje_iva=10,
            monto_iva=0,
            descuento_linea=descuento,
            subtotal=precio - descuento,
        )
        db.session.add(detalle)
        factura = DocumentoElectronico(
            id_venta=venta.id_venta,
            tipo_documento=TIPO_FACTURA,
            estado=ESTADO_APROBADO,
            cdc='1' * 44,
            establecimiento='001',
            punto='001',
            numero='0000001',
            timbrado='12345678',
            fecha_generado=datetime.utcnow(),
            api_documento_id='fac70000-0000-4000-8000-000000000001',
        )
        db.session.add(factura)
        db.session.commit()
        return venta, detalle, factura

    def _devolucion(self, venta, detalle, cantidad=1):
        monto = float(detalle.precio_unitario or 0) * cantidad
        devolucion = Devolucion(
            id_venta=venta.id_venta,
            id_usuario=self.admin.id_usuario,
            id_sesion_caja=self.sesion.id_sesion,
            motivo='Producto fallado',
            accion_stock='retorno_stock',
            monto_total=monto,
            metodo_reembolso='efectivo',
        )
        db.session.add(devolucion)
        db.session.flush()
        db.session.add(DetalleDevolucion(
            id_devolucion=devolucion.id_devolucion,
            id_producto=self.producto.id_producto,
            id_detalle_venta_original=detalle.id_detalle_venta,
            cantidad=cantidad,
            precio_unitario=detalle.precio_unitario,
            subtotal=monto,
        ))
        db.session.commit()
        return devolucion

    def _perfil(self):
        return {
            'ruc': '80012345',
            'sifen_mode': 'test',
            'address': 'Avda. Mcal. López 1234',
            'stamps': [
                {
                    'id': 'aaaaaaaa-0000-4000-8000-000000000001',
                    'number': '12345678', 'establishment': '001',
                    'expedition_point': '001', 'document_type': 1,
                    'valid_from': '2026-01-01',
                },
                {
                    'id': 'bbbbbbbb-0000-4000-8000-000000000005',
                    'number': '12345679', 'establishment': '001',
                    'expedition_point': '001', 'document_type': 5,
                    'valid_from': '2026-01-01',
                },
            ],
            'sifen_config': {
                'certificate': {'fingerprint_sha256': 'abc'},
                'csc': 'configured',
            },
        }

    def _api(self, capturadas, estado='PENDING_BATCH'):
        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if ruta == '/sifen/electronic-documents/':
                capturadas.append(kwargs.get('json'))
                return {
                    'id': 'nc000000-0000-4000-8000-000000000001',
                    'cdc': '5' * 44,
                    'status': estado,
                    'status_display': 'Pendiente de lote',
                    'transmits': True,
                }, None
            raise AssertionError(f'ruta inesperada: {ruta}')
        return _solicitar

    # -------------------------------------------------------------- pruebas

    def test_nota_credito_feliz(self):
        from facturacion_electronica.services import emitir_nota_credito, obtener_documento

        venta, detalle, factura = self._venta_facturada()
        devolucion = self._devolucion(venta, detalle)
        cuerpos = []

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   self._api(cuerpos)):
            nota, error = emitir_nota_credito(devolucion, 2)

        self.assertIsNone(error)
        self.assertEqual(nota.tipo_documento, TIPO_NOTA_CREDITO)
        self.assertEqual(nota.cdc, '5' * 44)
        self.assertEqual(nota.id_documento_asociado, factura.id)
        self.assertEqual(nota.id_devolucion, devolucion.id_devolucion)

        cuerpo = cuerpos[0]
        self.assertEqual(cuerpo['document_type'], TIPO_NOTA_CREDITO)
        self.assertEqual(cuerpo['stamp'], 'bbbbbbbb-0000-4000-8000-000000000005')
        self.assertEqual(cuerpo['associated']['cdc'], '1' * 44)
        self.assertNotIn('document_number', cuerpo['associated'])  # sólo en asociados impresos
        self.assertEqual(cuerpo['credit_debit'], {'motive': 2, 'motive_desc': 'Devolución'})
        self.assertEqual(cuerpo['lines'][0]['unit_price'], '100000')

        # La NC no reemplaza a la factura como documento de la venta.
        self.assertEqual(obtener_documento(venta.id_venta).id, factura.id)

    def test_la_nota_de_credito_tiene_su_propio_correlativo(self):
        from facturacion_electronica.services import emitir_nota_credito
        from facturacion_electronica.services.numeracion_service import peek_proximo_numero

        venta, detalle, _factura = self._venta_facturada()
        # La factura ya consumió el 0000001 de su propio rango.
        from facturacion_electronica.services.numeracion_service import reservar_numero
        reservar_numero('001', '001', TIPO_FACTURA)
        db.session.commit()

        devolucion = self._devolucion(venta, detalle)
        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   self._api([])):
            nota, error = emitir_nota_credito(devolucion, 2)

        self.assertIsNone(error)
        self.assertEqual(nota.numero, '0000001')
        self.assertEqual(peek_proximo_numero('001', '001', TIPO_FACTURA), '0000002')
        self.assertEqual(peek_proximo_numero('001', '001', TIPO_NOTA_CREDITO), '0000002')

    def test_no_se_acredita_una_factura_que_no_esta_aprobada(self):
        from facturacion_electronica.services import emitir_nota_credito

        venta, detalle, factura = self._venta_facturada()
        factura.estado = ESTADO_FIRMADO
        db.session.commit()
        devolucion = self._devolucion(venta, detalle)

        nota, error = emitir_nota_credito(devolucion, 2)
        self.assertIsNone(nota)
        self.assertIn('aprobada', error)

    def test_una_devolucion_no_genera_dos_notas(self):
        from facturacion_electronica.services import emitir_nota_credito

        venta, detalle, _factura = self._venta_facturada()
        devolucion = self._devolucion(venta, detalle)

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   self._api([])):
            _nota, error = emitir_nota_credito(devolucion, 2)
            self.assertIsNone(error)
            _nota, error = emitir_nota_credito(devolucion, 2)

        self.assertIn('ya tiene una nota de crédito', error)
        self.assertEqual(
            DocumentoElectronico.query.filter_by(tipo_documento=TIPO_NOTA_CREDITO).count(), 1)

    def test_motivo_fuera_del_catalogo_no_se_emite(self):
        from facturacion_electronica.services import emitir_nota_credito

        venta, detalle, _factura = self._venta_facturada()
        devolucion = self._devolucion(venta, detalle)

        _nota, error = emitir_nota_credito(devolucion, 99)
        self.assertIn('motivo del catálogo', error)

    def test_se_acredita_lo_facturado_y_se_avisa_la_diferencia(self):
        """La devolución reembolsa el precio de lista; la factura cobró con
        descuento. La NC va por lo facturado y el aviso queda a la vista."""
        from facturacion_electronica.services import emitir_nota_credito
        from facturacion_electronica.services.nota_credito import advertencias

        venta, detalle, _factura = self._venta_facturada(precio=100000, descuento=20000)
        devolucion = self._devolucion(venta, detalle)

        avisos = advertencias(devolucion)
        self.assertTrue(any('descuento' in a for a in avisos))

        cuerpos = []
        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   self._api(cuerpos)):
            _nota, error = emitir_nota_credito(devolucion, 2)

        self.assertIsNone(error)
        self.assertEqual(cuerpos[0]['lines'][0]['unit_price'], '80000')

    def test_el_job_reintenta_la_nota_sin_convertirla_en_factura(self):
        from facturacion_electronica.services import emitir_nota_credito
        from facturacion_electronica.services.proveedores.fachada import avanzar_documento

        venta, detalle, _factura = self._venta_facturada()
        devolucion = self._devolucion(venta, detalle)

        def _caido(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if metodo == 'GET':
                return {'results': []}, None
            return None, 'La API tardó demasiado en responder.'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _caido):
            nota, error = emitir_nota_credito(devolucion, 2)
        self.assertIsNotNone(error)
        self.assertEqual(nota.estado, ESTADO_ERROR)
        self.assertIsNone(nota.api_documento_id)

        cuerpos = []
        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   self._api(cuerpos)):
            error = avanzar_documento(nota)

        self.assertIsNone(error)
        self.assertEqual(cuerpos[0]['document_type'], TIPO_NOTA_CREDITO)
        self.assertEqual(nota.numero, '0000001')

    def test_sin_timbrado_de_nota_de_credito_en_la_api(self):
        from facturacion_electronica.services import emitir_nota_credito

        venta, detalle, _factura = self._venta_facturada()
        devolucion = self._devolucion(venta, detalle)
        perfil = self._perfil()
        perfil['stamps'] = [perfil['stamps'][0]]  # sólo el de factura

        def _solicitar(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return perfil, None
            raise AssertionError('no se debe intentar el alta sin timbrado')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _solicitar):
            nota, error = emitir_nota_credito(devolucion, 2)

        self.assertIn('nota de crédito', error)
        self.assertEqual(nota.estado, ESTADO_ERROR)

    def test_el_reintento_reserva_el_numero_que_el_primer_intento_no_pudo(self):
        """Si falla la reserva del correlativo, el job no puede postear igual.

        El alta manda `document_number: documento.numero`. Con la reserva
        fallada ese campo queda en None y el reintento posteaba una nota sin
        número, que es justo lo que la API exige que pongamos nosotros.
        """
        from facturacion_electronica.services import emitir_nota_credito
        from facturacion_electronica.services.proveedores.fachada import avanzar_documento

        venta, detalle, _factura = self._venta_facturada()
        devolucion = self._devolucion(venta, detalle)

        def _solo_perfil(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            raise AssertionError('no se debe postear una NC sin número')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   _solo_perfil), \
             patch('facturacion_electronica.services.proveedores.api.reservar_numero',
                   return_value=(None, 'El timbrado llegó a su último número.')):
            nota, error = emitir_nota_credito(devolucion, 2)

        self.assertIsNotNone(error)
        self.assertIsNone(nota.numero)

        cuerpos = []
        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   self._api(cuerpos)):
            error = avanzar_documento(nota)

        self.assertIsNone(error)
        self.assertEqual(nota.numero, '0000001')
        self.assertEqual(cuerpos[0]['document_number'], '0000001')

    def test_el_job_no_acredita_una_devolucion_anulada(self):
        from facturacion_electronica.services import emitir_nota_credito
        from facturacion_electronica.services.proveedores.fachada import avanzar_documento

        venta, detalle, _factura = self._venta_facturada()
        devolucion = self._devolucion(venta, detalle)

        def _caido(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if metodo == 'GET':
                return {'results': []}, None
            return None, 'La API tardó demasiado en responder.'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _caido):
            nota, _error = emitir_nota_credito(devolucion, 2)

        # Entre el intento fallido y el reintento, la devolución se anula.
        devolucion.estado = 'anulada'
        db.session.commit()

        def _no_debe_postear(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            raise AssertionError('no se debe postear la NC de una devolución anulada')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   _no_debe_postear):
            error = avanzar_documento(nota)

        self.assertIn('anulada', (error or '').lower())

    def test_el_job_no_acredita_una_factura_con_baja_pedida(self):
        """Si la cancelación de la factura ya está pedida, la NC sobra."""
        from facturacion_electronica import ESTADO_API_CANCELACION_PENDIENTE
        from facturacion_electronica.services import emitir_nota_credito
        from facturacion_electronica.services.proveedores.fachada import avanzar_documento

        venta, detalle, factura = self._venta_facturada()
        devolucion = self._devolucion(venta, detalle)

        def _caido(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            if metodo == 'GET':
                return {'results': []}, None
            return None, 'La API tardó demasiado en responder.'

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar', _caido):
            nota, _error = emitir_nota_credito(devolucion, 2)

        factura.respuesta_codigo = ESTADO_API_CANCELACION_PENDIENTE
        db.session.commit()

        def _no_debe_postear(config, metodo, ruta, **kwargs):
            if ruta == '/sifen/me/':
                return self._perfil(), None
            raise AssertionError('no se debe postear la NC de una factura en baja')

        with patch('facturacion_electronica.services.proveedores.api_client.solicitar',
                   _no_debe_postear):
            error = avanzar_documento(nota)

        self.assertIn('cancelación', (error or '').lower())

    def test_la_emision_manual_rechaza_una_devolucion_anulada(self):
        from facturacion_electronica.services import emitir_nota_credito

        venta, detalle, _factura = self._venta_facturada()
        devolucion = self._devolucion(venta, detalle)
        devolucion.estado = 'anulada'
        db.session.commit()

        nota, error = emitir_nota_credito(devolucion, 2)
        self.assertIsNone(nota)
        self.assertIn('anulada', (error or '').lower())

    def test_el_motor_propio_tambien_emite_notas(self):
        """El circuito de la NC existe en los dos motores. El propio arma y
        firma el DE acá mismo (su prueba completa vive en el archivo
        `..._nota_credito_propio`); lo que acá importa es que la fachada no lo
        mande al mensaje de "operación no disponible" del contrato."""
        from facturacion_electronica.services import capacidades, emitir_nota_credito
        from facturacion_electronica.services import generacion_service, nota_credito_service

        config = FacturacionElectronicaConfig.obtener()
        config.proveedor = 'propio'
        config.cert_path = '/fake/cert.p12'
        config.cert_password = 'clave'
        config.csc = 'ABCD0000000000000000000000000000'
        config.csc_id = '0001'
        db.session.commit()

        self.assertTrue(capacidades()['notas_credito'])

        venta, detalle, _factura = self._venta_facturada()
        devolucion = self._devolucion(venta, detalle)

        xml = ('<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
               '<DE Id="05042812925001001000000112026022419853987481"><dDVId>0</dDVId>'
               '</DE></rDE>')
        with patch.object(nota_credito_service, 'generar_xml', return_value=(xml, None)),              patch.object(generacion_service, 'firmar_xml', return_value=('<rDE/>', None)),              patch.object(generacion_service, 'generar_qr', return_value=('<rDE/>', None)):
            nota, error = emitir_nota_credito(devolucion, 2)

        self.assertIsNone(error)
        self.assertEqual(nota.tipo_documento, TIPO_NOTA_CREDITO)


if __name__ == '__main__':
    unittest.main()
