import unittest
from unittest.mock import patch

from app import create_app
from app.services.inteligencia.panel import construir_resumen_dashboard
from app.utils.bi_context import (
    construir_resumen_dashboard_desde_panel,
    construir_url_producto,
    obtener_resumen_dashboard_inteligencia_cacheado,
)


class _UsuarioPrueba:
    def __init__(self, id_usuario, permisos=None, id_cliente=None, admin=False):
        self.id_usuario = id_usuario
        self.id_cliente = id_cliente
        self.is_authenticated = True
        self._permisos = set(permisos or [])
        self._admin = admin

    def es_admin(self):
        return self._admin

    def tiene_permiso(self, codigo_permiso):
        return codigo_permiso in self._permisos


class TestInteligenciaBiContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')

    def test_resumen_bi_context_cachea_por_usuario(self):
        usuario = _UsuarioPrueba(9101, permisos={'ver_reportes'}, id_cliente=77)

        with self.app.app_context():
            with patch(
                'app.services.inteligencia.obtener_resumen_dashboard_inteligencia',
                return_value={'alertas_activas': 4, 'riesgo_stock': 2},
            ) as resumen_mock:
                primero = obtener_resumen_dashboard_inteligencia_cacheado(usuario)
                segundo = obtener_resumen_dashboard_inteligencia_cacheado(usuario)

        self.assertEqual(primero, segundo)
        self.assertEqual(primero['alertas_activas'], 4)
        self.assertEqual(resumen_mock.call_count, 1)

    def test_construir_url_producto_usa_busqueda_si_no_hay_permiso_de_edicion(self):
        usuario = _UsuarioPrueba(9102, permisos={'ver_inventario'})

        with self.app.test_request_context('/'):
            url = construir_url_producto(
                usuario,
                {'id_producto': 15, 'codigo': 'INV-IDLE-001', 'nombre': 'Mate encajonado'},
            )

        self.assertIn('/productos/', url)
        self.assertIn('buscar=INV-IDLE-001', url)

    def test_resumen_dashboard_usa_total_de_alertas_y_no_lista_truncada(self):
        resumen = construir_resumen_dashboard(
            {'total_para_activar': 6},
            {'riesgo_count': 2, 'inmovilizado_count': 3},
            {'campanas': [{}, {}]},
            7,
        )

        self.assertEqual(resumen['alertas_activas'], 7)
        self.assertEqual(resumen['acciones_label'], '7 acciones')

    def test_construir_resumen_desde_panel_reutiliza_total_de_alertas(self):
        resumen = construir_resumen_dashboard_desde_panel({
            'clientes': {'total_para_activar': 5},
            'stock': {'riesgo_count': 2, 'inmovilizado_count': 1},
            'campanas': {'campanas': [{}, {}, {}]},
            'alertas_activas_total': 6,
            'acciones_hoy': [{}, {}, {}, {}],
        })

        self.assertIsNotNone(resumen)
        self.assertEqual(resumen['alertas_activas'], 6)
        self.assertEqual(resumen['campanas_sugeridas'], 3)


if __name__ == '__main__':
    unittest.main()
