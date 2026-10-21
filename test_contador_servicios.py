"""Área Contador/a: lo propio de este sistema al portarla de sistema_silvio_cel.

- Es IVA paraguayo: en una instalación con otra moneda (R$ en Brasil) el área
  no aparece ni se puede abrir.
- El listado de facturas electrónicas suma los filtros que pide el resumen
  ("atencion", "anulado") y el de ambiente, sin cambiar lo que ya listaba.
"""
from datetime import date, datetime

from app import db
from app.models import Configuracion, Usuario, Venta
from facturacion_electronica import (
    AMBIENTE_PRODUCCION,
    AMBIENTE_TEST,
    CLAVE_FACTURACION_ELECTRONICA_ACTIVO,
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_ERROR,
    ESTADO_INUTILIZADO,
    ESTADO_RECHAZADO,
    TIPO_FACTURA,
)
from facturacion_electronica.models import DocumentoElectronico

from test_facturacion_electronica_proveedor_base import BaseProveedorApi

MES = '2026-09'
EN_EL_MES = datetime(2026, 9, 15, 15, 0)


class TestContadorServicios(BaseProveedorApi):
    def setUp(self):
        super().setUp()
        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'false')
        db.session.commit()
        self.http = self.app.test_client()
        with self.http.session_transaction() as sesion:
            sesion['_user_id'] = str(Usuario.query.filter_by(username='admin').first().id_usuario)
            sesion['_fresh'] = True

    def test_en_guaranies_se_ve_el_area(self):
        respuesta = self.http.get(f'/contador/iva?mes={MES}')

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('data-sidebar-trigger="contador"', respuesta.get_data(as_text=True))

    def test_con_otra_moneda_no_hay_area_contador(self):
        Configuracion.establecer('moneda_simbolo', 'R$')
        Configuracion.establecer('moneda_locale', 'pt-BR')
        db.session.commit()

        self.assertEqual(self.http.get(f'/contador/iva?mes={MES}').status_code, 302)
        self.assertEqual(self.http.get(f'/contador/iva/detalle?mes={MES}&fila=compras').status_code, 403)
        pantalla = self.http.get('/ventas/')
        self.assertEqual(pantalla.status_code, 200)
        html = pantalla.get_data(as_text=True)
        self.assertIn('data-sidebar-trigger="finanzas"', html)
        self.assertNotIn('data-sidebar-trigger="contador"', html)

        # Tampoco se ofrece cargar la factura de un gasto (IVA paraguayo).
        from decimal import Decimal
        from app.models import GastoCorriente, PagoGastoCorriente

        gasto = GastoCorriente(nombre='Luz', categoria='servicios', monto_estimado=Decimal('100'),
                               dia_vencimiento=10, activo=True)
        db.session.add(gasto)
        db.session.flush()
        pago = PagoGastoCorriente(id_gasto_corriente=gasto.id_gasto_corriente, periodo_anio=2026, periodo_mes=9,
                                  fecha_vencimiento=date(2026, 9, 10), fecha_pago=date(2026, 9, 12),
                                  monto_estimado=100, monto_pagado=100, estado='pagado')
        db.session.add(pago)
        db.session.commit()
        ficha = self.http.get(f'/gastos-corrientes/{gasto.id_gasto_corriente}')
        self.assertEqual(ficha.status_code, 200)
        self.assertNotIn('Cargar factura (IVA)', ficha.get_data(as_text=True))
        factura = self.http.post(f'/contador/gasto-pago/{pago.id_pago_gasto_corriente}/factura', data={'numero': '1'})
        self.assertEqual(factura.status_code, 403)

    def test_informe_aclara_que_el_debito_no_incluye_las_ventas(self):
        """Sin el número de factura en el POS, un débito de Gs. 0 no debe leerse como "no hubo ventas"."""
        from app.services.resumen_contadora_informe import VENTAS_SIN_NUMERO_EN_ESTE_SISTEMA, informe_del_mes

        self.assertIn(VENTAS_SIN_NUMERO_EN_ESTE_SISTEMA, informe_del_mes(date(2026, 9, 1), False)['avisos'])
        self.assertNotIn(VENTAS_SIN_NUMERO_EN_ESTE_SISTEMA, informe_del_mes(date(2026, 9, 1), True)['avisos'])

    def _documento(self, numero, estado, ambiente=AMBIENTE_PRODUCCION):
        venta = Venta(id_cliente=self.cliente.id_cliente, id_sesion_caja=self.sesion.id_sesion,
                      subtotal=11000, total=11000, total_iva_10=1000, fecha_venta=EN_EL_MES)
        db.session.add(venta)
        db.session.flush()
        db.session.add(DocumentoElectronico(id_venta=venta.id_venta, tipo_documento=TIPO_FACTURA,
                                            establecimiento='001', punto='001', numero=numero,
                                            estado=estado, ambiente=ambiente))
        db.session.commit()

    def test_listado_suma_filtros_del_resumen_sin_cambiar_los_de_antes(self):
        from facturacion_electronica.services.listado_documentos import consulta_documentos, listar_documentos

        self._documento('0000001', ESTADO_APROBADO)
        self._documento('0000002', ESTADO_RECHAZADO)
        self._documento('0000003', ESTADO_ERROR)
        self._documento('0000004', ESTADO_CANCELADO)
        self._documento('0000005', ESTADO_INUTILIZADO)
        self._documento('0000006', ESTADO_APROBADO, ambiente=AMBIENTE_TEST)
        desde, hasta = date(2026, 9, 1), date(2026, 9, 30)

        def contar(estado='', ambiente=''):
            return consulta_documentos(desde, hasta, estado, ambiente=ambiente)[0].count()

        self.assertEqual(contar('atencion'), 2)
        self.assertEqual(contar('anulado'), 2)
        self.assertEqual(contar('rechazado'), 1)
        self.assertEqual(contar('aprobado'), 2)                                  # sin ambiente: todos
        self.assertEqual(contar('aprobado', ambiente=AMBIENTE_PRODUCCION), 1)
        self.assertEqual(listar_documentos(desde, hasta)['cantidad'], 6)
        self.assertEqual(listar_documentos(desde, hasta, estado='anulado', ambiente=AMBIENTE_PRODUCCION)['cantidad'], 2)
