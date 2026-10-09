"""Guardado de la configuración del emisor.

El caso que motivó estas pruebas: cargar el CSC en el campo del ID. Son 32
caracteres en una columna de 8, y contra MySQL estricto eso no trunca — tira
1406 y la pantalla devuelve 500 sin decir qué campo está mal. Contra SQLite,
que es lo que corre la suite, pasaba sin ruido.
"""
import unittest

from app import create_app, db
from facturacion_electronica.models import FacturacionElectronicaConfig
from facturacion_electronica.services.config_service import guardar_configuracion


class TestGuardarConfiguracion(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _form(self, **extra):
        datos = {
            'proveedor': 'propio',
            'ambiente': 'test',
            'razon_social': 'JANELIPY GROUP E.A.S.',
            'ruc': '80178105',
            'dv_ruc': '1',
            'timbrado_numero': '19128252',
            'establecimiento': '001',
            'punto_expedicion': '001',
            'actividad_economica_codigo': '47723',
            'csc': '36966c71e51a8ff4e1f7d212dbf25afd',
            'csc_id': '0001',
        }
        datos.update(extra)
        return datos

    def test_el_csc_en_el_campo_del_id_avisa_en_vez_de_romper(self):
        # El valor de maqueta del CSC pegado en "ID del CSC".
        config, error = guardar_configuracion(
            self._form(csc_id='ABCD0000000000000000000000000000')
        )

        self.assertIsNotNone(error)
        self.assertIn('ID del CSC', error)
        self.assertIn('32', error)
        # El aviso tiene que nombrar la confusión concreta, no sólo el largo.
        self.assertIn('cambiados de lugar', error)
        # Y no se guarda nada: media configuración nueva sería peor.
        self.assertIsNone(config.razon_social)

    def test_un_campo_cualquiera_que_no_entra_tambien_avisa(self):
        _config, error = guardar_configuracion(self._form(dv_ruc='12345'))

        self.assertIsNotNone(error)
        self.assertIn('Dígito verificador', error)
        self.assertNotIn('cambiados de lugar', error)

    def test_los_datos_correctos_se_guardan(self):
        config, error = guardar_configuracion(self._form())

        self.assertIsNone(error)
        self.assertEqual(config.ruc, '80178105')
        self.assertEqual(config.csc_id, '0001')
        self.assertEqual(config.timbrado_numero, '19128252')

        guardada = FacturacionElectronicaConfig.obtener()
        self.assertEqual(guardada.razon_social, 'JANELIPY GROUP E.A.S.')


if __name__ == '__main__':
    unittest.main()
