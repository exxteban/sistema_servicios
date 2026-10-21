"""Pantalla "Resumen para la contadora": IVA del mes y lo pendiente para cerrar.

El débito sale del XML que se mandó a SIFEN (lo que la contadora ve en
Marangatu) y el crédito sólo de compras con número de factura: sin comprobante
ese IVA no se deduce, así que va como pendiente.
"""
import unittest
from datetime import date, datetime

from app import db
from facturacion_electronica import (
    AMBIENTE_PRODUCCION,
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_FIRMADO,
    ESTADO_RECHAZADO,
    TIPO_FACTURA,
    TIPO_NOTA_CREDITO,
)
from facturacion_electronica.models import DocumentoElectronico, FacturacionElectronicaConfig

from test_facturacion_electronica_proveedor_base import BaseProveedorApi

MES = '2026-09'
EN_EL_MES = datetime(2026, 9, 15, 15, 0)   # mediodía en Asunción: lejos de los bordes UTC


def _xml(iva10=0, base10=0, iva5=0, base5=0, exenta=0):
    total = base10 + iva10 + base5 + iva5 + exenta
    return (
        '<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><DE><gTotSub>'
        f'<dSubExe>{exenta}</dSubExe><dBaseGrav5>{base5}</dBaseGrav5><dIVA5>{iva5}</dIVA5>'
        f'<dBaseGrav10>{base10}</dBaseGrav10><dIVA10>{iva10}</dIVA10>'
        f'<dTotGralOpe>{total}</dTotGralOpe></gTotSub></DE></rDE>'
    )


class TestResumenContadora(BaseProveedorApi):
    def setUp(self):
        super().setUp()
        from app.models import Configuracion
        from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'true')
        config = FacturacionElectronicaConfig.obtener()
        config.ambiente = AMBIENTE_PRODUCCION
        db.session.commit()

    def _get(self, url):
        from app.models import Usuario

        usuario = Usuario.query.filter_by(username='admin').first()
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion['_user_id'] = str(usuario.id_usuario)
            sesion['_fresh'] = True
        return cliente.get(url)

    def _documento(self, numero, estado, xml=None, tipo=TIPO_FACTURA, ambiente=AMBIENTE_PRODUCCION,
                   venta_iva10=0):
        venta = self._venta()
        venta.fecha_venta = EN_EL_MES
        venta.total_iva_10 = venta_iva10
        documento = DocumentoElectronico(
            id_venta=venta.id_venta, tipo_documento=tipo, establecimiento='001', punto='001',
            numero=numero, estado=estado, ambiente=ambiente, xml_firmado=xml,
            fecha_generado=EN_EL_MES,
        )
        db.session.add(documento)
        db.session.commit()
        return documento

    def _compra(self, numero_factura, total, iva10, estado='completada'):
        from app.models import Compra, Proveedor, Usuario

        proveedor = Proveedor.query.filter_by(nombre='Distribuidora Sur').first()
        if proveedor is None:
            proveedor = Proveedor(nombre='Distribuidora Sur')
            db.session.add(proveedor)
            db.session.flush()
        compra = Compra(
            numero_factura=numero_factura, id_proveedor=proveedor.id_proveedor,
            id_usuario=Usuario.query.filter_by(username='admin').first().id_usuario,
            fecha_compra=date(2026, 9, 10), subtotal=total, total=total,
            total_iva_10=iva10, total_iva_5=0, estado=estado,
        )
        db.session.add(compra)
        db.session.commit()
        return compra

    def test_debito_credito_y_pendientes_del_mes(self):
        from app.services.resumen_contadora import resumen_del_mes

        self._documento('0000001', ESTADO_APROBADO, _xml(iva10=10000, base10=100000))
        self._documento('0000002', ESTADO_APROBADO, _xml(iva5=500, base5=10000, exenta=3000))
        self._documento('0000003', ESTADO_APROBADO, _xml(iva10=1000, base10=10000), tipo=TIPO_NOTA_CREDITO)
        self._documento('0000004', ESTADO_RECHAZADO)
        self._documento('0000005', ESTADO_FIRMADO)
        self._documento('0000006', ESTADO_CANCELADO, _xml(iva10=99999, base10=999990))
        # Pruebas de TEST de antes de pasar a producción: no son nada.
        self._documento('0000900', ESTADO_APROBADO, _xml(iva10=77777, base10=777770), ambiente='test')
        self._compra('001-001-0000123', 55000, 5000)
        self._compra('', 22000, 2000)
        self._compra('001-001-0000999', 110000, 10000, estado='anulada')
        self._compra('US-0042', 800000, 0)     # usado comprado a un particular: no es factura
        self._compra('', 15000, 0)             # exenta sin número: no es pendiente del IVA

        r = resumen_del_mes(date(2026, 9, 1), True, AMBIENTE_PRODUCCION)

        self.assertEqual(r['documentos']['ventas']['cantidad'], 2)
        self.assertEqual(r['documentos']['ventas']['exenta'], 3000)
        self.assertEqual(r['debito'], 10000 + 500 - 1000)
        self.assertEqual(r['credito'], 5000)
        self.assertEqual(r['compras']['cantidad'], 1)
        self.assertEqual(r['compras']['total'], 55000)
        self.assertEqual(r['saldo'], 9500 - 5000)
        self.assertEqual(r['documentos']['rechazados'], 1)
        self.assertEqual(r['documentos']['sin_respuesta'], 1)
        self.assertEqual(r['documentos']['canceladas'], 1)
        self.assertEqual(r['sin_comprobante']['cantidad'], 1)
        self.assertEqual(r['sin_comprobante']['iva_en_riesgo'], 2000)
        # La compra con factura no tiene timbrado: también es pendiente.
        self.assertEqual(r['controles']['compras_sin_timbrado']['cantidad'], 1)
        self.assertEqual(r['pendientes'], 4)

    def test_factura_sin_xml_usa_la_venta_y_lo_avisa(self):
        from app.services.resumen_contadora import resumen_del_mes

        self._documento('0000001', ESTADO_APROBADO, xml=None, venta_iva10=9091)
        # NC que anula una venta entera, sin copia del XML: resta el IVA de esa venta.
        self._documento('0000002', ESTADO_APROBADO, xml=None, venta_iva10=4545,
                        tipo=TIPO_NOTA_CREDITO)

        r = resumen_del_mes(date(2026, 9, 1), True, AMBIENTE_PRODUCCION)

        self.assertEqual(r['documentos']['ventas_estimadas'], 1)
        self.assertEqual(r['documentos']['nc_estimadas'], 1)
        self.assertEqual(r['debito'], 9091 - 4545)
        self.assertEqual(r['pendientes'], 2)

    def test_pantalla_muestra_el_mes_y_lleva_a_los_rechazados(self):
        self._documento('0000001', ESTADO_APROBADO, _xml(iva10=10000, base10=100000))
        self._documento('0000004', ESTADO_RECHAZADO)
        self._compra('', 22000, 2000)

        html = self._get(f'/contador/iva?mes={MES}').get_data(as_text=True)

        self.assertIn('Resumen para el/la contador/a', html)
        self.assertIn('₲ 10.000', html)
        self.assertIn('Pendiente para cerrar el mes', html)
        self.assertIn('estado=atencion', html)
        self.assertIn('Distribuidora Sur', html)

    def test_muestra_las_anuladas_del_mes_y_flechas_de_mes(self):
        from facturacion_electronica import ESTADO_INUTILIZADO

        cancelada = self._documento('0000006', ESTADO_CANCELADO, _xml(iva10=1000, base10=10000))
        cancelada.motivo_cancelacion = 'Cliente pidió otro RUC'
        inutilizado = self._documento('0000007', ESTADO_INUTILIZADO)
        inutilizado.motivo_cancelacion = 'Corte de luz antes de transmitir'
        db.session.commit()

        html = self._get(f'/contador/iva?mes={MES}').get_data(as_text=True)

        self.assertIn('Facturas anuladas del mes (2)', html)
        # Dos pestañas; la que viene en la URL es la que se abre (las flechas la conservan).
        self.assertIn("vista: 'iva'", html)
        self.assertIn('name="vista"', html)
        anuladas = self._get(f'/contador/iva?mes={MES}&vista=anuladas').get_data(as_text=True)
        self.assertIn("vista: 'anuladas'", anuladas)
        self.assertIn('001-001-0000006', html)
        self.assertIn('Cliente pidió otro RUC', html)
        self.assertIn('Número inutilizado', html)
        self.assertIn('estado=anulado', html)
        self.assertIn("'2026-08'", html)   # flecha al mes anterior
        self.assertIn("'2026-10'", html)   # y al siguiente

        listado = self._get(
            '/facturacion-electronica/documentos?estado=anulado&desde=2026-09-01&hasta=2026-09-30'
            f'&ambiente={AMBIENTE_PRODUCCION}').get_data(as_text=True)
        self.assertIn('001-001-0000006', listado)
        self.assertIn('001-001-0000007', listado)

    def test_detalle_de_cada_fila_cierra_con_el_cuadro(self):
        from app.services.resumen_contadora import resumen_del_mes
        from app.services.resumen_contadora_detalle import detalle_fila

        factura = self._documento('0000001', ESTADO_APROBADO, _xml(iva10=10000, base10=100000))
        self._documento('0000002', ESTADO_APROBADO, _xml(iva5=500, base5=10000, exenta=3000))
        nota = self._documento('0000003', ESTADO_APROBADO, _xml(iva10=1000, base10=10000), tipo=TIPO_NOTA_CREDITO)
        nota.id_documento_asociado = factura.id
        db.session.commit()
        self._compra('001-001-0000123', 55000, 5000)
        self._compra('', 22000, 2000)

        r = resumen_del_mes(date(2026, 9, 1), True, AMBIENTE_PRODUCCION)
        for clave, bloque in (('ventas', r['documentos']['ventas']),
                              ('notas', r['documentos']['notas_credito']),
                              ('compras', r['compras'])):
            d = detalle_fila(date(2026, 9, 1), clave, AMBIENTE_PRODUCCION)
            self.assertEqual(len(d['filas']), bloque['cantidad'], clave)
            for k in ('exenta', 'base5', 'iva5', 'base10', 'iva10', 'total'):
                self.assertAlmostEqual(d['totales'][k], bloque[k], msg=f'{clave}.{k}')
        notas = detalle_fila(date(2026, 9, 1), 'notas', AMBIENTE_PRODUCCION)
        self.assertEqual(notas['filas'][0]['afecta'], '001-001-0000001')
        self.assertIsNone(detalle_fila(date(2026, 9, 1), 'cualquiera', AMBIENTE_PRODUCCION))

        html = self._get(f'/contador/iva/detalle?mes={MES}&fila=ventas').get_data(as_text=True)
        self.assertIn('001-001-0000001', html)
        self.assertIn('₲ 10.000', html)
        compras = self._get(f'/contador/iva/detalle?mes={MES}&fila=compras').get_data(as_text=True)
        self.assertIn('Distribuidora Sur', compras)
        self.assertEqual(self._get(f'/contador/iva/detalle?mes={MES}&fila=x').status_code, 404)

        pantalla = self._get(f'/contador/iva?mes={MES}').get_data(as_text=True)
        self.assertIn("abrir('ventas')", pantalla)
        self.assertIn('/contador/iva/detalle?mes=2026-09', pantalla)

    def test_mes_vecino_cruza_el_anio(self):
        from app.services.resumen_contadora import mes_vecino

        self.assertEqual(mes_vecino(date(2026, 1, 1), -1), date(2025, 12, 1))
        self.assertEqual(mes_vecino(date(2026, 12, 1), 1), date(2027, 1, 1))

    def test_estimacion_sin_xml_aplica_descuento_y_detalle_coincide(self):
        from app.services.resumen_contadora import resumen_del_mes
        from app.services.resumen_contadora_detalle import detalle_fila

        documento = self._documento('0000001', ESTADO_APROBADO, venta_iva10=10000)
        documento.venta.subtotal = 110000
        documento.venta.total = 99000
        db.session.commit()
        r = resumen_del_mes(date(2026, 9, 1), True, AMBIENTE_PRODUCCION)
        self.assertEqual(r['debito'], 9000)
        self.assertEqual(r['documentos']['ventas_estimadas'], 1)
        detalle = detalle_fila(date(2026, 9, 1), 'ventas', AMBIENTE_PRODUCCION)
        t = detalle['totales']
        self.assertEqual(t['iva10'], r['debito'])
        self.assertEqual(sum(t[k] for k in ('exenta', 'base5', 'iva5', 'base10', 'iva10')), t['total'])

    def test_sin_facturacion_electronica_usa_las_ventas_en_papel(self):
        from app.models import Configuracion
        from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'false')
        db.session.commit()
        self._compra('001-001-0000123', 55000, 5000)

        respuesta = self._get(f'/contador/iva?mes={MES}')
        html = respuesta.get_data(as_text=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('Ventas con número de factura', html)
        self.assertNotIn('Facturas electrónicas aprobadas', html)
        self.assertIn('₲ 5.000', html)

    def test_mes_por_defecto_es_el_anterior(self):
        from app.services.resumen_contadora import mes_por_defecto, parse_mes, rango_del_mes

        self.assertEqual(mes_por_defecto(date(2026, 10, 19)), date(2026, 9, 1))
        self.assertEqual(mes_por_defecto(date(2026, 1, 5)), date(2025, 12, 1))
        self.assertEqual(rango_del_mes(date(2026, 2, 1)), (date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(parse_mes('2026-09'), date(2026, 9, 1))
        self.assertIsNone(parse_mes('cualquiera'))


if __name__ == '__main__':
    unittest.main()
