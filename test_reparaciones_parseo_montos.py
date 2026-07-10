import unittest

from app import db
import test_caja_reparacion


class ReparacionesBase(unittest.TestCase):
    def setUp(self):
        return test_caja_reparacion.TestCajaReparacion.setUp(self)

    def tearDown(self):
        return test_caja_reparacion.TestCajaReparacion.tearDown(self)

    def _crear_reparacion(self, *args, **kwargs):
        return test_caja_reparacion.TestCajaReparacion._crear_reparacion(self, *args, **kwargs)


class TestReparacionesParseoMontos(ReparacionesBase):
    def test_nuevo_reparacion_interpreta_separador_de_miles(self):
        from app.models import Reparacion

        resp = self.client.post(
            '/reparaciones/nuevo',
            data={
                'cliente_id': str(self.cliente.id_cliente),
                'id_usuario_vendedor': str(self.admin.id_usuario),
                'tipo_equipo': 'Celular',
                'marca_modelo': 'Xiaomi Redmi Note',
                'imei_serie': 'IMEI-PARSE-001',
                'falla_reportada': 'No enciende',
                'diagnostico_tecnico': 'Bateria agotada',
                'solucion': 'Cambio de bateria',
                'costo_estimado': '50.000',
                'costo_final': '160.000',
                'abono': '35.000',
            },
            follow_redirects=False,
        )

        self.assertEqual(resp.status_code, 302)

        reparacion = Reparacion.query.order_by(Reparacion.id_reparacion.desc()).first()
        self.assertIsNotNone(reparacion)
        self.assertEqual(reparacion.imei_serie, 'IMEI-PARSE-001')
        self.assertAlmostEqual(float(reparacion.costo_estimado or 0), 50000.0)
        self.assertAlmostEqual(float(reparacion.costo_final or 0), 160000.0)
        self.assertAlmostEqual(float(reparacion.abono or 0), 35000.0)
        self.assertAlmostEqual(float(reparacion.saldo_pendiente or 0), 125000.0)

    def test_actualizar_costos_interpreta_separador_de_miles(self):
        reparacion = self._crear_reparacion(costo_final=120000, abono=0)

        resp = self.client.post(
            f'/reparaciones/{reparacion.id_reparacion}/costos',
            data={
                'costo_estimado': '50.000',
                'costo_final': '160.000',
                'abono': '35.000',
            },
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json() or {}
        self.assertTrue(data.get('success'))
        self.assertAlmostEqual(float(data.get('costo_estimado') or 0), 50000.0)
        self.assertAlmostEqual(float(data.get('costo_final_base') or 0), 160000.0)
        self.assertAlmostEqual(float(data.get('abono') or 0), 35000.0)
        self.assertAlmostEqual(float(data.get('saldo_pendiente') or 0), 125000.0)

        db.session.refresh(reparacion)
        self.assertAlmostEqual(float(reparacion.costo_estimado or 0), 50000.0)
        self.assertAlmostEqual(float(reparacion.costo_final or 0), 160000.0)
        self.assertAlmostEqual(float(reparacion.abono or 0), 35000.0)
        self.assertAlmostEqual(float(reparacion.saldo_pendiente or 0), 125000.0)


class TestParseoMontosFormatoBrasil(unittest.TestCase):
    """El parser debe interpretar bien el formato brasileño (Real): punto para
    miles y coma para decimales, sin romper el formato guaraní (miles con punto,
    sin decimales)."""

    def _f(self, valor):
        from app.routes.reparaciones.base import _a_float_seguro
        return _a_float_seguro(valor)

    def test_real_con_miles_y_centavos(self):
        self.assertAlmostEqual(self._f('1.234,56'), 1234.56)
        self.assertAlmostEqual(self._f('R$ 2.350,90'), 2350.90)
        self.assertAlmostEqual(self._f('1.000,00'), 1000.00)

    def test_real_solo_centavos(self):
        self.assertAlmostEqual(self._f('10,50'), 10.50)
        self.assertAlmostEqual(self._f('0,50'), 0.50)
        self.assertAlmostEqual(self._f('999,99'), 999.99)
        self.assertAlmostEqual(self._f('1234,5'), 1234.5)

    def test_guarani_miles_no_se_rompe(self):
        self.assertAlmostEqual(self._f('50.000'), 50000.0)
        self.assertAlmostEqual(self._f('1.500'), 1500.0)
        self.assertAlmostEqual(self._f('2.500'), 2500.0)
        self.assertAlmostEqual(self._f('100'), 100.0)


if __name__ == '__main__':
    unittest.main()
