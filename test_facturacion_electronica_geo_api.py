"""Tabla geográfica del modo API: la de la SET, guardada y renovada sola.

El motor propio sigue con la tabla de TIPS, que es la que valida al generar el
XML. La del modo API sale del catálogo del proveedor (1.8.0) y trae los
distritos que TIPS no conoce: Tavapy (269, Alto Paraná) es el de las pruebas.
"""
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import url_for

from app import create_app, db
from facturacion_electronica.services import geo
from facturacion_electronica.services.config_service import guardar_configuracion
from facturacion_electronica.services.proveedores import api_geo

TAVAPY = 269
ALTO_PARANA = 11


def _catalogo_api(ruta):
    """Respuestas de `api_client.solicitar` para el catálogo geográfico."""
    if ruta.endswith('/departments/'):
        return [{'code': ALTO_PARANA, 'description': 'ALTO PARANA'}], None
    if ruta.endswith('/districts/'):
        return [{'code': TAVAPY, 'description': 'TAVAPY', 'department_code': ALTO_PARANA}], None
    if '/cities/' in ruta:
        return [{
            'code': 9001, 'description': 'UNA CIUDAD CON UN NOMBRE MUY LARGO DE VERDAD',
            'sifen_name': 'UNA CIUDAD CON UN NOMBRE MUY L',
            'district_code': TAVAPY, 'department_code': ALTO_PARANA,
        }], None
    return None, 'ruta inesperada'


class TestTablaPorProveedor(unittest.TestCase):
    def test_el_modo_api_conoce_distritos_que_tips_no(self):
        self.assertTrue(any(d['codigo'] == TAVAPY for d in geo.distritos_de(ALTO_PARANA, 'api')))
        self.assertFalse(any(d['codigo'] == TAVAPY for d in geo.distritos_de(ALTO_PARANA)))
        self.assertEqual(geo.descripcion_distrito(TAVAPY, 'api'), 'TAVAPY')
        self.assertIsNone(geo.descripcion_distrito(TAVAPY, 'propio'))

    def test_el_motor_propio_no_cambia(self):
        self.assertEqual(geo.descripcion_distrito('161'), 'ÑEMBY')
        self.assertEqual(geo.descripcion_ciudad(5975, 'propio'), 'ÑEMBY')

    def test_la_copia_del_codigo_respeta_el_largo_de_sifen(self):
        tabla = api_geo._snapshot()
        for clave in ('distritos', 'ciudades'):
            self.assertTrue(all(len(f['descripcion']) <= 30 for f in tabla[clave]), clave)


class TestRenovacion(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.carpeta = tempfile.mkdtemp()
        self.ruta = os.path.join(self.carpeta, api_geo.NOMBRE_ARCHIVO)
        self.parches = [
            patch.object(api_geo, '_ruta_cache', return_value=self.ruta),
            patch.object(api_geo.api_client, 'base_url', return_value='https://fe.test/api/v1'),
        ]
        for parche in self.parches:
            parche.start()
        api_geo._ultimo_fallo['cuando'] = None
        api_geo._cache.update(mtime=None, tabla=None)
        self.config = SimpleNamespace(proveedor='api')

    def tearDown(self):
        for parche in self.parches:
            parche.stop()
        api_geo._ultimo_fallo['cuando'] = None
        api_geo._cache.update(mtime=None, tabla=None)
        shutil.rmtree(self.carpeta, ignore_errors=True)
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _solicitar(self, llamadas, falla=False):
        def fake(_config, _metodo, ruta, **_kwargs):
            llamadas.append(ruta)
            return (None, 'La API respondió 503') if falla else _catalogo_api(ruta)
        return patch.object(api_geo.api_client, 'solicitar', side_effect=fake)

    def test_sin_descargar_nunca_usa_la_copia_del_codigo(self):
        self.assertIs(api_geo.tabla(), api_geo._snapshot())
        self.assertTrue(api_geo.vencida())

    def test_vencida_la_descarga_y_la_guarda(self):
        llamadas = []
        with self._solicitar(llamadas):
            self.assertIsNone(api_geo.actualizar_si_vencida(self.config))

        self.assertTrue(os.path.exists(self.ruta))
        self.assertFalse(api_geo.vencida())
        # Ciudades por departamento: exigen filtro.
        self.assertIn(f'/sifen/catalogs/cities/?department={ALTO_PARANA}', llamadas)
        ciudades = geo.ciudades_de(TAVAPY, 'api')
        self.assertEqual(ciudades[0]['descripcion'], 'UNA CIUDAD CON UN NOMBRE MUY L')

        # Vigente: la pasada siguiente del job no llama a nada.
        llamadas.clear()
        with self._solicitar(llamadas):
            api_geo.actualizar_si_vencida(self.config)
        self.assertEqual(llamadas, [])

    def test_si_la_api_falla_sigue_la_copia_y_no_reintenta_en_cada_pasada(self):
        llamadas = []
        with self._solicitar(llamadas, falla=True):
            self.assertIn('503', api_geo.actualizar_si_vencida(self.config))
            self.assertFalse(os.path.exists(self.ruta))
            self.assertTrue(any(d['codigo'] == TAVAPY for d in geo.distritos_de(ALTO_PARANA, 'api')))

            llamadas.clear()
            self.assertIsNone(api_geo.actualizar_si_vencida(self.config))
        self.assertEqual(llamadas, [])

    def test_el_motor_propio_no_descarga_nada(self):
        llamadas = []
        with self._solicitar(llamadas):
            api_geo.actualizar_si_vencida(SimpleNamespace(proveedor='propio'))
        self.assertEqual(llamadas, [])

    def test_guardar_en_modo_api_toma_los_nombres_de_su_tabla(self):
        config, error = guardar_configuracion({
            'proveedor': 'api',
            'departamento_codigo': str(ALTO_PARANA),
            'distrito_codigo': str(TAVAPY),
        })
        self.assertIsNone(error)
        self.assertEqual(config.distrito_desc, 'TAVAPY')

    def test_la_lista_de_distritos_sigue_al_proveedor_del_formulario(self):
        from app.models import Usuario

        admin = Usuario.query.filter_by(username='admin').first()
        cliente = self.app.test_client()
        with cliente.session_transaction() as sesion:
            sesion['_user_id'] = str(admin.id_usuario)
            sesion['_fresh'] = True
        with self.app.test_request_context():
            url = url_for('facturacion_electronica.geo_distritos')

        api = cliente.get(f'{url}?departamento={ALTO_PARANA}&proveedor=api').get_json()
        propio = cliente.get(f'{url}?departamento={ALTO_PARANA}&proveedor=propio').get_json()

        self.assertTrue(any(d['codigo'] == TAVAPY for d in api))
        self.assertFalse(any(d['codigo'] == TAVAPY for d in propio))


if __name__ == '__main__':
    unittest.main()
