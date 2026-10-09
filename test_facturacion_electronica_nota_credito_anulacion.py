"""Anular una factura mal emitida con una nota de crédito, sin devolución.

El caso que no estaba cubierto: el comprobante salió mal (cliente equivocado,
monto mal, venta facturada dos veces) y no vuelve mercadería. Dentro de las 48h
se cancela con el evento; pasado ese plazo la única salida es acreditar el
total con una NC.
"""
import unittest
from datetime import datetime
from unittest.mock import patch

from app import create_app, db
from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_GENERADO,
    TIPO_FACTURA,
    TIPO_NOTA_CREDITO,
)


XML_NC = '<DE Id="01801781050010010000001202609210000000001"/>'


class TestNotaCreditoDeAnulacion(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import (
            Categoria, Cliente, DetalleVenta, Producto, SesionCaja, Usuario, Venta,
        )
        from facturacion_electronica.models import (
            DocumentoElectronico,
            FacturacionElectronicaConfig,
        )

        admin = Usuario.query.filter_by(username='admin').first()
        sesion = SesionCaja(
            id_caja=1, id_usuario=admin.id_usuario, monto_inicial=0, estado='abierta',
        )
        db.session.add(sesion)
        db.session.flush()

        # Identificado a propósito: SIFEN no acepta acreditarle a un
        # receptor innominado.
        cliente = Cliente(nombre='Alfio Oviedo', ruc_ci='4281292')
        db.session.add(cliente)
        db.session.flush()

        self.venta = Venta(
            id_cliente=cliente.id_cliente,
            id_sesion_caja=sesion.id_sesion,
            subtotal=200000, total=200000,
            fecha_venta=datetime.utcnow(), estado='completada',
        )
        db.session.add(self.venta)
        db.session.flush()

        categoria = Categoria.query.first()
        if categoria is None:
            categoria = Categoria(nombre='General')
            db.session.add(categoria)
            db.session.flush()
        producto = Producto(
            codigo='NCA-001', nombre='Producto NC anulacion',
            id_categoria=categoria.id_categoria,
            precio_compra=5000, precio_venta=50000, stock_actual=10,
        )
        db.session.add(producto)
        db.session.flush()
        # Dos líneas, una con descuento adentro del subtotal: la NC tiene que
        # acreditar lo facturado, no el precio de lista.
        db.session.add_all([
            DetalleVenta(
                id_venta=self.venta.id_venta, id_producto=producto.id_producto,
                cantidad=2, precio_unitario=50000, precio_original=50000,
                monto_iva=8182,
                subtotal=90000, porcentaje_iva=10,
            ),
            DetalleVenta(
                id_venta=self.venta.id_venta, id_producto=producto.id_producto,
                cantidad=1, precio_unitario=110000, precio_original=110000,
                monto_iva=10000,
                subtotal=110000, porcentaje_iva=10,
            ),
        ])

        self.factura = DocumentoElectronico(
            id_venta=self.venta.id_venta, tipo_documento=TIPO_FACTURA,
            estado=ESTADO_APROBADO, cdc='0' * 44, numero='0000001',
            establecimiento='001', punto='001', timbrado='80178105',
        )
        db.session.add(self.factura)

        config = FacturacionElectronicaConfig.obtener()
        config.ruc = '80178105'
        config.dv_ruc = '1'
        config.razon_social = 'Janelipy Group E.A.S.'
        config.timbrado_numero = '80178105'
        config.cert_path = '/fake/cert.p12'
        config.cert_password = 'clave'
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_acredita_el_total_facturado_y_no_el_precio_de_lista(self):
        """El subtotal de la línea ya tiene el descuento adentro. Acreditar el
        precio de lista sería declarar menos IVA del que se cobró."""
        from facturacion_electronica.services import emision_service, nota_credito_service

        with patch.object(nota_credito_service, 'generar_xml',
                          return_value=(XML_NC, None)) as mock:
            doc, error = emision_service.generar_nota_credito_correccion(
                self.venta, motivo=2, descripcion='Facturado al cliente equivocado',
            )

        self.assertIsNone(error)
        self.assertEqual(doc.tipo_documento, TIPO_NOTA_CREDITO)
        self.assertIsNone(doc.id_devolucion)
        self.assertEqual(doc.id_documento_asociado, self.factura.id)

        data = mock.call_args.args[1]
        total = sum(float(i['precioUnitario']) * float(i['cantidad'])
                    for i in data['items'])
        self.assertEqual(total, 200000)
        # La descripción libre viaja en el documento.
        self.assertEqual(data['descripcion'], 'Facturado al cliente equivocado')

    def test_la_nc_lleva_su_propio_correlativo(self):
        """Factura 001-001-0000001 y NC 001-001-0000001 conviven en el mismo
        timbrado: si comiera el rango de facturas, SIFEN rechaza."""
        from facturacion_electronica.services import emision_service, nota_credito_service

        with patch.object(nota_credito_service, 'generar_xml', return_value=(XML_NC, None)):
            doc, error = emision_service.generar_nota_credito_correccion(
                self.venta, motivo=2,
            )

        self.assertIsNone(error)
        self.assertEqual(doc.numero, '0000001')
        self.assertNotEqual(doc.id, self.factura.id)

    def test_no_se_anula_una_factura_que_sifen_no_aprobo(self):
        from facturacion_electronica.services import emision_service

        self.factura.estado = ESTADO_GENERADO
        db.session.commit()

        _doc, error = emision_service.generar_nota_credito_correccion(
            self.venta, motivo=2,
        )
        self.assertIn('aprobada por SIFEN', error)

    def test_no_se_emite_dos_veces(self):
        """Dos NC por el total acreditarían el doble de lo facturado."""
        from facturacion_electronica.services import emision_service, nota_credito_service

        with patch.object(nota_credito_service, 'generar_xml', return_value=(XML_NC, None)):
            doc, error = emision_service.generar_nota_credito_correccion(
                self.venta, motivo=2,
            )
            self.assertIsNone(error)
            doc.estado = ESTADO_APROBADO
            db.session.commit()

            _otra, error = emision_service.generar_nota_credito_correccion(
                self.venta, motivo=2,
            )

        self.assertIn('no se puede emitir otra', error)

    def test_hace_falta_un_motivo_del_catalogo(self):
        from facturacion_electronica.services import emision_service

        _doc, error = emision_service.generar_nota_credito_correccion(
            self.venta, motivo=None,
        )
        self.assertIn('motivo del catálogo', error)

    # -- La consecuencia sobre la anulación de la venta --------------------

    def test_aprobada_la_nc_la_venta_se_puede_anular(self):
        """La factura sigue 'aprobado' para siempre —una NC no cambia el estado
        del DE que corrige— pero fiscalmente ya no queda nada en pie."""
        from facturacion_electronica.services import emision_service, nota_credito_service
        from facturacion_electronica.services.guarda import (
            documento_impide_anular_venta,
        )

        self.assertTrue(documento_impide_anular_venta(self.factura))

        with patch.object(nota_credito_service, 'generar_xml', return_value=(XML_NC, None)):
            doc, error = emision_service.generar_nota_credito_correccion(
                self.venta, motivo=2,
            )
        self.assertIsNone(error)

        # Mientras SIFEN no la apruebe, la factura sigue viva.
        self.assertTrue(documento_impide_anular_venta(self.factura))

        doc.estado = ESTADO_APROBADO
        db.session.commit()
        self.assertFalse(documento_impide_anular_venta(self.factura))

    def test_una_nc_de_devolucion_no_destraba_la_anulacion(self):
        """Una devolución puede ser parcial: la factura sigue viva por el resto,
        y anular la venta entera dejaría un ingreso declarado que no existió."""
        from facturacion_electronica.models import DocumentoElectronico
        from facturacion_electronica.services.guarda import (
            documento_impide_anular_venta,
        )

        db.session.add(DocumentoElectronico(
            id_venta=self.venta.id_venta, tipo_documento=TIPO_NOTA_CREDITO,
            estado=ESTADO_APROBADO, id_documento_asociado=self.factura.id,
            id_devolucion=99, numero='0000001', establecimiento='001', punto='001',
        ))
        db.session.commit()

        self.assertTrue(documento_impide_anular_venta(self.factura))
