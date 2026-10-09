"""Anular una venta tiene que dejar la caja y la contabilidad como antes de venderla.

Regresiones portadas del sistema padre (`test_ventas_anulacion_vuelto.py`,
`test_contabilidad_anulacion_periodo.py`):

- Con vuelto: el POS registra el ingreso bruto ('venta') y el vuelto aparte
  ('vuelto'). La anulacion tiene que revertir los dos; si revierte solo el
  ingreso, el arqueo queda con un faltante igual al vuelto.
- La contabilidad ubica la reversa en la fecha de la auditoria de la
  anulacion: sin esa fila el cobro queda sumado para siempre.
"""
from datetime import timedelta

from app import db
from app.models import Auditoria, MovimientoCaja, SesionCaja, Venta
from app.routes.caja.contabilidad_report import calcular_informe_contable_rango
from app.utils.helpers import today_local, utc_bounds_for_local_dates

import unittest

import test_caja_anulaciones


class _EscenarioCaja(unittest.TestCase):
    """Reusa el escenario de `TestCajaAnulaciones` sin volver a correr sus tests."""

    def setUp(self):
        self._escenario = test_caja_anulaciones.TestCajaAnulaciones()
        self._escenario.setUp()
        self.client = self._escenario.client

    def tearDown(self):
        self._escenario.tearDown()

    def __getattr__(self, nombre):
        if nombre.startswith('_crear'):
            return getattr(self.__dict__['_escenario'], nombre)
        raise AttributeError(nombre)


class TestAnulacionCaja(_EscenarioCaja):
    def _vender_con_vuelto(self, producto, entregado):
        from app.models import Cliente, MetodoPago, Usuario

        admin = Usuario.query.filter_by(username='admin').first()
        efectivo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        resp = self.client.post('/ventas/procesar', json={
            'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
            'pagos': [{'id_metodo_pago': int(efectivo.id_metodo_pago), 'monto': entregado}],
            'id_cliente': int(Cliente.query.first().id_cliente),
            'id_usuario_vendedor': int(admin.id_usuario),
            'client_request_id': 'anulacion-con-vuelto',
        })
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return int(resp.get_json()['id_venta'])

    def _neto_caja_de_venta(self, venta_id):
        movs = MovimientoCaja.query.filter(
            MovimientoCaja.referencia_id == venta_id,
            MovimientoCaja.referencia_tipo.in_(('venta', 'vuelto', 'anulacion_venta')),
        ).all()
        return sum(float(m.monto) * (1 if m.tipo == 'ingreso' else -1) for m in movs)

    def test_anular_venta_con_vuelto_deja_la_caja_en_cero(self):
        producto = self._crear_producto_simple(codigo='ANUL-VUELTO-1', precio=150000)
        venta_id = self._vender_con_vuelto(producto, 200000)
        self.assertEqual(self._neto_caja_de_venta(venta_id), 150000.0)

        resp = self.client.post(f'/ventas/{venta_id}/anular', data={})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(db.session.get(Venta, venta_id).estado, 'anulada')
        self.assertEqual(self._neto_caja_de_venta(venta_id), 0.0)

    def test_anulacion_en_el_mismo_periodo_no_suma_ni_resta(self):
        producto = self._crear_producto_simple(codigo='ANUL-CONTAB-1', precio=50000)
        venta_id = self._crear_venta_efectivo(producto, 'anulacion-contab-mismo-dia')
        limites = utc_bounds_for_local_dates(today_local(), today_local())
        self.assertEqual(calcular_informe_contable_rango(*limites)['resultado_caja_mes'], 50000)

        self.client.post(f'/ventas/{venta_id}/anular', data={})
        self.assertEqual(calcular_informe_contable_rango(*limites)['resultado_caja_mes'], 0)

    def test_anulacion_posterior_va_al_periodo_de_la_reversa(self):
        producto = self._crear_producto_simple(codigo='ANUL-CONTAB-2', precio=50000)
        venta_id = self._crear_venta_efectivo(producto, 'anulacion-contab-posterior')
        ayer = today_local() - timedelta(days=1)
        limites_ayer = utc_bounds_for_local_dates(ayer, ayer)
        instante = limites_ayer[0] + timedelta(hours=1)
        db.session.get(Venta, venta_id).fecha_venta = instante
        MovimientoCaja.query.filter_by(referencia_tipo='venta', referencia_id=venta_id).update(
            {'fecha_movimiento': instante})
        db.session.commit()

        self.client.post(f'/ventas/{venta_id}/anular', data={})
        limites_hoy = utc_bounds_for_local_dates(today_local(), today_local())
        self.assertEqual(calcular_informe_contable_rango(*limites_ayer)['resultado_caja_mes'], 50000)
        self.assertEqual(calcular_informe_contable_rango(*limites_hoy)['resultado_caja_mes'], -50000)

    def test_sin_auditoria_la_venta_no_se_anula(self):
        """La fecha de la reversa sale de la auditoria: sin ella, nada se anula."""
        from unittest import mock

        producto = self._crear_producto_simple(codigo='ANUL-AUDIT-1', precio=50000)
        venta_id = self._crear_venta_efectivo(producto, 'anulacion-sin-auditoria')
        stock_antes = float(producto.stock_actual)

        with mock.patch('app.routes.ventas.parte4.registrar_auditoria', return_value=None):
            self.client.post(f'/ventas/{venta_id}/anular', data={})

        db.session.expire_all()
        self.assertEqual(db.session.get(Venta, venta_id).estado, 'completada')
        self.assertEqual(float(db.session.get(type(producto), producto.id_producto).stock_actual), stock_antes)
        self.assertEqual(self._neto_caja_de_venta(venta_id), 50000.0)
        self.assertIsNone(Auditoria.query.filter_by(accion='anular_venta', referencia_id=venta_id).first())

    def test_anular_con_vuelto_el_mismo_dia_deja_la_contabilidad_en_cero(self):
        producto = self._crear_producto_simple(codigo='ANUL-VUELTO-2', precio=150000)
        venta_id = self._vender_con_vuelto(producto, 200000)
        limites = utc_bounds_for_local_dates(today_local(), today_local())
        self.assertEqual(calcular_informe_contable_rango(*limites)['resultado_caja_mes'], 150000)

        self.client.post(f'/ventas/{venta_id}/anular', data={})
        informe = calcular_informe_contable_rango(*limites)
        self.assertEqual(informe['resultado_caja_mes'], 0)
        conceptos = {c['concepto'] for c in informe.get('conceptos') or []}
        self.assertNotIn('Ingresos Manuales / Ajustes', conceptos)


class TestDevolucionPantalla(_EscenarioCaja):
    """El endpoint de devolucion existia pero ninguna pantalla lo llamaba."""

    def test_detalle_ofrece_devolver_y_muestra_lo_devuelto(self):
        producto = self._crear_producto_simple(codigo='DEVOL-UI-1', precio=50000)
        venta_id = self._crear_venta_efectivo(producto, 'devolucion-pantalla')
        venta = db.session.get(Venta, venta_id)
        detalle_id = int(venta.detalles.first().id_detalle_venta)

        html = self.client.get(f'/ventas/{venta_id}').get_data(as_text=True)
        self.assertIn('Registrar devolución', html)
        self.assertIn(f'data-devolucion-item="{detalle_id}"', html)
        self.assertIn('function confirmarDevolucion', html)

        resp = self.client.post(f'/ventas/{venta_id}/devolucion', json={
            'items': [{'id_detalle_venta': detalle_id, 'cantidad': 1}],
            'motivo': 'Vino fallado',
            'accion_stock': 'retorno_stock',
            'metodo_reembolso': 'efectivo',
        })
        self.assertEqual(resp.status_code, 200, resp.get_json())

        html = self.client.get(f'/ventas/{venta_id}').get_data(as_text=True)
        self.assertIn('Devoluciones de esta venta', html)
        self.assertIn('Vino fallado', html)
        # La unica unidad ya volvio: no queda nada para devolver.
        self.assertIn('ya devuelto: 1 de 1', html)
