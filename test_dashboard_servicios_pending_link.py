import unittest

from app.services.dashboard_servicios import resolver_destino_cobros_pendientes_dashboard


class TestDashboardServiciosPendingLink(unittest.TestCase):
    def test_cajero_con_acceso_a_caja_abre_cola_pendiente(self):
        destino = resolver_destino_cobros_pendientes_dashboard(
            can_crear_venta=True,
            can_ver_ventas=True,
            can_ver_caja=True,
            can_tomar_cola_cobro=True,
            modo_cobro_exclusivo_cajero=True,
            date_from='2026-05-22',
            date_to='2026-05-22',
        )

        self.assertEqual(destino['endpoint'], 'caja.cobros_pendientes')
        self.assertEqual(destino['params'], {})
        self.assertEqual(destino['label'], 'Abrir cobros')

    def test_vendedor_en_modo_exclusivo_va_a_enviadas(self):
        destino = resolver_destino_cobros_pendientes_dashboard(
            can_crear_venta=True,
            can_ver_ventas=True,
            can_ver_caja=False,
            can_tomar_cola_cobro=False,
            modo_cobro_exclusivo_cajero=True,
            date_from='2026-05-22',
            date_to='2026-05-22',
        )

        self.assertEqual(destino['endpoint'], 'ventas.registro_vendedor_enviadas')
        self.assertEqual(destino['params'], {'estado': 'pendiente'})
        self.assertEqual(destino['label'], 'Ver enviadas')

    def test_usuario_con_pos_directo_abre_pos(self):
        destino = resolver_destino_cobros_pendientes_dashboard(
            can_crear_venta=True,
            can_ver_ventas=True,
            can_ver_caja=False,
            can_tomar_cola_cobro=False,
            modo_cobro_exclusivo_cajero=False,
            date_from='2026-05-22',
            date_to='2026-05-22',
        )

        self.assertEqual(destino['endpoint'], 'ventas.pos')
        self.assertEqual(destino['params'], {})
        self.assertEqual(destino['label'], 'Abrir POS')

    def test_sin_permiso_de_cobro_vuelve_al_listado(self):
        destino = resolver_destino_cobros_pendientes_dashboard(
            can_crear_venta=False,
            can_ver_ventas=True,
            can_ver_caja=False,
            can_tomar_cola_cobro=False,
            modo_cobro_exclusivo_cajero=False,
            date_from='2026-05-01',
            date_to='2026-05-22',
        )

        self.assertEqual(destino['endpoint'], 'ventas.listar')
        self.assertEqual(
            destino['params'],
            {'desde': '2026-05-01', 'hasta': '2026-05-22'},
        )
        self.assertEqual(destino['label'], 'Ver movimientos')


if __name__ == '__main__':
    unittest.main()
