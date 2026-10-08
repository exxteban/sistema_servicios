"""Nota de crédito con el **motor propio** (iTiDE 5 contra SIFEN directo).

La NC de la API externa tiene su propio archivo; acá se cubre el circuito que
arma, firma y envía el XML nosotros mismos. Lo que se cuida:

- el DE de la NC lleva `gCamNCDE` (motivo del catálogo) y `gCamDEAsoc` con el
  CDC de la factura, y **no** lleva condición de la operación: la NC acredita,
  no cobra;
- la NC tiene su **propio correlativo**: factura 0000001 y NC 0000001 conviven
  dentro del mismo timbrado;
- la fecha del DE es la de **emisión de la NC**, no la de la venta: contra la
  fecha de la venta la ventana de 72h de SIFEN nacía vencida y la nota de una
  factura de la semana pasada no se podía enviar nunca;
- la NC no pasa a ser "el documento" de la venta (el POS, el KuDE y la guarda
  de anulación tienen que seguir mirando la factura);
- regenerar no cambia el CDC ni consume otro número del rango.
"""
import unittest
from datetime import date, datetime, timedelta
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
    ESTADO_CANCELADO,
    ESTADO_ERROR,
    ESTADO_GENERADO,
    TIPO_FACTURA,
    TIPO_NOTA_CREDITO,
)
from facturacion_electronica.models import (
    DocumentoElectronico,
    FacturacionElectronicaConfig,
    SecuenciaNumeracionDE,
)

CDC_FACTURA = '01042812925001001000000112026022419853987480'
CDC_NOTA = '05042812925001001000000112026022419853987481'


def _xml_con_cdc(cdc):
    return (
        '<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
        f'<DE Id="{cdc}"><dDVId>0</dDVId></DE></rDE>'
    )


class TestNotaCreditoMotorPropio(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

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
            codigo='NCP-001', nombre='Producto NC propio', id_categoria=categoria.id_categoria,
            precio_compra=5000, precio_venta=100000, stock_actual=10,
        )
        db.session.add(self.producto)
        db.session.commit()

        config = FacturacionElectronicaConfig.obtener()
        config.proveedor = 'propio'
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
        self.config = config

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # ------------------------------------------------------------ fixtures

    def _venta(self, precio=100000, descuento=0, fecha=None):
        venta = Venta(
            id_cliente=self.cliente.id_cliente,
            id_sesion_caja=self.sesion.id_sesion,
            subtotal=precio - descuento,
            total=precio - descuento,
            fecha_venta=fecha or datetime.utcnow(),
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
        db.session.commit()
        self.detalle_venta = detalle
        return venta

    def _facturar(self, venta, estado=ESTADO_APROBADO, numero='0000001'):
        """Factura aprobada de la venta, como la dejaría el circuito propio."""
        factura = DocumentoElectronico(
            id_venta=venta.id_venta,
            tipo_documento=TIPO_FACTURA,
            cdc=CDC_FACTURA,
            establecimiento='001',
            punto='001',
            numero=numero,
            estado=estado,
            xml_firmado='<rDE/>',
            fecha_generado=venta.fecha_venta,
        )
        db.session.add(factura)
        db.session.commit()
        return factura

    def _devolucion(self, venta, cantidad=1, precio=100000, estado='completada'):
        devolucion = Devolucion(
            id_venta=venta.id_venta,
            id_usuario=self.admin.id_usuario,
            id_sesion_caja=self.sesion.id_sesion,
            motivo='Producto fallado',
            accion_stock='retorno_stock',
            monto_total=cantidad * precio,
            metodo_reembolso='efectivo',
            estado=estado,
        )
        db.session.add(devolucion)
        db.session.flush()
        db.session.add(DetalleDevolucion(
            id_devolucion=devolucion.id_devolucion,
            id_producto=self.producto.id_producto,
            id_detalle_venta_original=self.detalle_venta.id_detalle_venta,
            cantidad=cantidad,
            precio_unitario=precio,
            subtotal=cantidad * precio,
        ))
        db.session.commit()
        return devolucion

    def _emitir(self, devolucion, motivo=2):
        """Emite la NC con el microservicio Node simulado."""
        from facturacion_electronica.services import emision_service, generacion_service, nota_credito_service

        with patch.object(nota_credito_service, 'generar_xml',
                          return_value=(_xml_con_cdc(CDC_NOTA), None)) as gen, \
             patch.object(generacion_service, 'firmar_xml',
                          return_value=('<rDE firmado="1"/>', None)), \
             patch.object(generacion_service, 'generar_qr',
                          return_value=('<rDE qr="1"/>', None)):
            documento, error = emision_service.emitir_nota_credito(devolucion, motivo)
        self.ultimo_payload = gen.call_args[0][1] if gen.call_args else None
        return documento, error

    # ------------------------------------------------------- el XML de la NC

    def test_data_de_la_nc_lleva_motivo_documento_asociado_y_no_condicion(self):
        from facturacion_electronica.services.data_builder import construir_data_nota_credito

        venta = self._venta()
        factura = self._facturar(venta)
        devolucion = self._devolucion(venta)

        data = construir_data_nota_credito(
            devolucion, self.config, factura, 2,
            numero='0000001', fecha=datetime.utcnow(),
        )

        self.assertEqual(data['tipoDocumento'], TIPO_NOTA_CREDITO)
        self.assertEqual(data['notaCreditoDebito'], {'motivo': 2})
        self.assertEqual(data['documentoAsociado']['cdc'], CDC_FACTURA)
        self.assertEqual(data['documentoAsociado']['formato'], 1)
        # La condición de la operación es de la factura: xmlgen ni siquiera la
        # valida para el tipo 5, y mandarla declararía cobros que no existieron.
        self.assertNotIn('condicion', data)
        self.assertNotIn('factura', data)
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['precioUnitario'], 100000)

    def test_la_nc_acredita_el_precio_facturado_no_el_reembolsado(self):
        """La línea tenía descuento: la factura declaró 90.000 y eso es lo que
        se acredita, aunque la devolución haya reembolsado el precio de lista."""
        from facturacion_electronica.services.data_builder import construir_data_nota_credito

        venta = self._venta(precio=100000, descuento=10000)
        factura = self._facturar(venta)
        devolucion = self._devolucion(venta, precio=100000)

        data = construir_data_nota_credito(
            devolucion, self.config, factura, 2,
            numero='0000001', fecha=datetime.utcnow(),
        )
        self.assertEqual(data['items'][0]['precioUnitario'], 90000)

    def test_la_fecha_del_de_es_la_de_la_nc_no_la_de_la_venta(self):
        from facturacion_electronica.services.data_builder import construir_data_nota_credito

        hace_un_mes = datetime.utcnow() - timedelta(days=30)
        venta = self._venta(fecha=hace_un_mes)
        factura = self._facturar(venta)
        devolucion = self._devolucion(venta)

        emitida = datetime.utcnow()
        data = construir_data_nota_credito(
            devolucion, self.config, factura, 2, numero='0000001', fecha=emitida,
        )
        self.assertNotIn(hace_un_mes.strftime('%Y-%m-%d'), data['fecha'])

    # ------------------------------------------------------------- emisión

    def test_emitir_nc_deja_el_documento_firmado_con_su_propio_correlativo(self):
        from facturacion_electronica.services.emision_service import generar_documento

        venta = self._venta()
        from facturacion_electronica.services import generacion_service
        with patch.object(generacion_service, 'generar_xml',
                          return_value=(_xml_con_cdc(CDC_FACTURA), None)):
            factura, error = generar_documento(venta)
        self.assertIsNone(error)
        self.assertEqual(factura.numero, '0000001')
        factura.estado = ESTADO_APROBADO
        db.session.commit()

        devolucion = self._devolucion(venta)
        nota, error = self._emitir(devolucion)

        self.assertIsNone(error)
        self.assertEqual(nota.tipo_documento, TIPO_NOTA_CREDITO)
        # Mismo timbrado, rangos distintos: la NC arranca en su propio 1.
        self.assertEqual(nota.numero, '0000001')
        self.assertEqual(nota.cdc, CDC_NOTA)
        self.assertEqual(nota.id_documento_asociado, factura.id)
        self.assertEqual(nota.id_devolucion, devolucion.id_devolucion)
        self.assertEqual(nota.nc_motivo, 2)
        self.assertEqual(nota.nc_motivo_desc, 'Devolución')
        self.assertIsNotNone(nota.xml_firmado)
        self.assertIsNotNone(nota.xml_qr)

        secuencias = {
            (s.tipo_documento, s.establecimiento, s.punto): s.ultimo_numero
            for s in SecuenciaNumeracionDE.query.all()
        }
        self.assertEqual(secuencias[(TIPO_FACTURA, '001', '001')], 1)
        self.assertEqual(secuencias[(TIPO_NOTA_CREDITO, '001', '001')], 1)

    def test_la_nc_no_se_convierte_en_el_documento_de_la_venta(self):
        from facturacion_electronica.services.emision_service import obtener_documento

        venta = self._venta()
        factura = self._facturar(venta)
        devolucion = self._devolucion(venta)
        nota, error = self._emitir(devolucion)
        self.assertIsNone(error)

        vigente = obtener_documento(venta.id_venta)
        self.assertEqual(vigente.id, factura.id)
        self.assertNotEqual(vigente.id, nota.id)

    def test_una_devolucion_no_genera_dos_notas_de_credito(self):
        venta = self._venta()
        self._facturar(venta)
        devolucion = self._devolucion(venta)

        primera, error = self._emitir(devolucion)
        self.assertIsNone(error)
        primera.estado = ESTADO_APROBADO
        db.session.commit()

        segunda, error = self._emitir(devolucion)
        self.assertIsNotNone(error)
        self.assertIn('ya figura como aprobado', error)
        self.assertEqual(segunda.id, primera.id)
        self.assertEqual(
            DocumentoElectronico.query.filter_by(tipo_documento=TIPO_NOTA_CREDITO).count(), 1,
        )
        secuencia = SecuenciaNumeracionDE.query.filter_by(
            tipo_documento=TIPO_NOTA_CREDITO,
        ).first()
        self.assertEqual(secuencia.ultimo_numero, 1)

    def test_regenerar_conserva_numero_codigo_y_fecha(self):
        """El CDC tiene que ser estable: un reintento no puede quemar otro
        número del rango ni mover la fecha de emisión."""
        venta = self._venta()
        self._facturar(venta)
        devolucion = self._devolucion(venta)

        nota, error = self._emitir(devolucion)
        self.assertIsNone(error)
        numero, codigo, fecha = nota.numero, nota.codigo_seguridad, nota.fecha_generado

        de_nuevo, error = self._emitir(devolucion)
        self.assertIsNone(error)
        self.assertEqual(de_nuevo.id, nota.id)
        self.assertEqual(de_nuevo.numero, numero)
        self.assertEqual(de_nuevo.codigo_seguridad, codigo)
        self.assertEqual(de_nuevo.fecha_generado, fecha)

    def test_no_se_acredita_una_factura_que_no_esta_aprobada(self):
        venta = self._venta()
        self._facturar(venta, estado=ESTADO_GENERADO)
        devolucion = self._devolucion(venta)

        nota, error = self._emitir(devolucion)
        self.assertIsNotNone(error)
        self.assertIn('aprobada', error)
        self.assertIsNone(nota)
        # Y no se consumió correlativo de notas de crédito.
        self.assertIsNone(SecuenciaNumeracionDE.query.filter_by(
            tipo_documento=TIPO_NOTA_CREDITO,
        ).first())

    def test_no_se_acredita_una_devolucion_anulada(self):
        venta = self._venta()
        self._facturar(venta)
        devolucion = self._devolucion(venta, estado='anulada')

        nota, error = self._emitir(devolucion)
        self.assertIsNotNone(error)
        self.assertIn('anulada', error.lower())
        self.assertIsNone(nota)

    def test_motivo_invalido_no_reserva_numero(self):
        venta = self._venta()
        self._facturar(venta)
        devolucion = self._devolucion(venta)

        nota, error = self._emitir(devolucion, motivo='99')
        self.assertIsNotNone(error)
        self.assertIn('motivo', error.lower())
        self.assertIsNone(SecuenciaNumeracionDE.query.filter_by(
            tipo_documento=TIPO_NOTA_CREDITO,
        ).first())

    def test_una_nc_cancelada_habilita_emitir_otra(self):
        venta = self._venta()
        self._facturar(venta)
        devolucion = self._devolucion(venta)

        primera, error = self._emitir(devolucion)
        self.assertIsNone(error)
        primera.estado = ESTADO_CANCELADO
        db.session.commit()

        segunda, error = self._emitir(devolucion)
        self.assertIsNone(error)
        self.assertNotEqual(segunda.id, primera.id)
        self.assertEqual(segunda.numero, '0000002')

    # -------------------------------------------------- ventana de 72h y job

    def test_la_nc_de_una_venta_vieja_se_puede_enviar(self):
        """La ventana de 72h se cuenta desde la emisión de la NC. Contra la
        fecha de la venta, acreditar una factura de la semana pasada era
        imposible: el envío se negaba antes de intentar."""
        from facturacion_electronica.services import emision_service, envio_service

        venta = self._venta(fecha=datetime.utcnow() - timedelta(days=7))
        self._facturar(venta)
        devolucion = self._devolucion(venta)
        nota, error = self._emitir(devolucion)
        self.assertIsNone(error)

        respuesta = {'ns2:dEstRes': 'Aprobado', 'ns2:dCodRes': '0260',
                     'ns2:dMsgRes': 'Autorización del DE satisfactoria',
                     'ns2:dProtAut': '50094059'}
        with patch.object(envio_service, 'enviar_de', return_value=(respuesta, None)):
            nota, error = emision_service.enviar_documento(nota)

        self.assertIsNone(error)
        self.assertEqual(nota.estado, ESTADO_APROBADO)

    def test_el_job_regenera_la_nc_como_nc_y_no_toca_la_factura(self):
        """`generar_documento` mira la factura de la venta: si el job pasara
        por ahí, la NC se quedaba sin XML y se reintentaba para siempre."""
        from facturacion_electronica.services import envio_service, generacion_service, nota_credito_service
        from facturacion_electronica.services.proveedores.propio import ProveedorPropio

        venta = self._venta()
        factura = self._facturar(venta)
        devolucion = self._devolucion(venta)
        nota, error = self._emitir(devolucion)
        self.assertIsNone(error)

        # Un fallo de transporte dejó la NC sin XML.
        nota.xml = None
        nota.xml_firmado = None
        nota.xml_qr = None
        nota.estado = ESTADO_GENERADO
        db.session.commit()

        respuesta = {'ns2:dEstRes': 'Aprobado', 'ns2:dCodRes': '0260'}
        with patch.object(nota_credito_service, 'generar_xml',
                          return_value=(_xml_con_cdc(CDC_NOTA), None)), \
             patch.object(generacion_service, 'firmar_xml',
                          return_value=('<rDE firmado="1"/>', None)), \
             patch.object(generacion_service, 'generar_qr',
                          return_value=('<rDE qr="1"/>', None)), \
             patch.object(envio_service, 'enviar_de', return_value=(respuesta, None)):
            error = ProveedorPropio().avanzar(nota)

        self.assertIsNone(error)
        db.session.refresh(nota)
        db.session.refresh(factura)
        self.assertEqual(nota.tipo_documento, TIPO_NOTA_CREDITO)
        self.assertEqual(nota.estado, ESTADO_APROBADO)
        # La factura quedó como estaba: el job no la regeneró por el camino.
        self.assertEqual(factura.estado, ESTADO_APROBADO)
        self.assertEqual(factura.numero, '0000001')

    # ----------------------------------------------------------------- KuDE

    def test_el_kude_de_la_nc_imprime_lo_acreditado_no_la_venta_entera(self):
        from facturacion_electronica.services.kude_service import construir_contexto_kude

        venta = self._venta(precio=100000)
        # Se venden 2 unidades y se devuelve 1.
        self.detalle_venta.cantidad = 2
        self.detalle_venta.subtotal = 200000
        venta.subtotal = venta.total = 200000
        db.session.commit()
        self._facturar(venta)
        devolucion = self._devolucion(venta, cantidad=1, precio=100000)
        nota, error = self._emitir(devolucion)
        self.assertIsNone(error)

        contexto = construir_contexto_kude(venta, nota)
        self.assertTrue(contexto['es_nota_credito'])
        self.assertEqual(contexto['titulo_documento'], 'NOTA DE CRÉDITO ELECTRÓNICA')
        self.assertEqual(contexto['total'], 100000)
        self.assertEqual(len(contexto['items']), 1)
        self.assertEqual(contexto['items'][0]['subtotal'], 100000)
        self.assertEqual(contexto['motivo_nc'], 'Devolución')
        self.assertEqual(contexto['fecha_documento'], nota.fecha_generado)

    def test_el_kude_de_la_nc_se_imprime_desde_la_ruta(self):
        """El papel se mira renderizado, no en la plantilla: la ruta imprimía
        siempre la factura de la venta, así que la NC no tenía comprobante."""
        from flask_login import login_user

        from facturacion_electronica.routes import kude

        venta = self._venta(precio=100000)
        self._facturar(venta)
        devolucion = self._devolucion(venta)
        nota, error = self._emitir(devolucion)
        self.assertIsNone(error)

        with self.app.test_request_context(
            '/facturacion-electronica/kude/%d?documento=%d&preview=1'
            % (venta.id_venta, nota.id),
        ):
            login_user(self.admin)
            html = kude(venta.id_venta)

        self.assertIn('NOTA DE CRÉDITO ELECTRÓNICA', html)
        self.assertIn('Devolución', html)
        self.assertIn(CDC_FACTURA, html)
        # El número impreso es el de la NC, no el de la factura.
        self.assertIn('001-001-%s' % nota.numero, html)
        self.assertNotIn('Condición:', html)

    def test_el_kude_de_la_factura_sigue_igual(self):
        from facturacion_electronica.services.kude_service import construir_contexto_kude

        venta = self._venta(precio=100000)
        factura = self._facturar(venta)

        contexto = construir_contexto_kude(venta, factura)
        self.assertFalse(contexto['es_nota_credito'])
        self.assertEqual(contexto['titulo_documento'], 'FACTURA ELECTRÓNICA')
        self.assertEqual(contexto['total'], 100000)
        self.assertEqual(contexto['fecha_documento'], venta.fecha_venta)


if __name__ == '__main__':
    unittest.main()
