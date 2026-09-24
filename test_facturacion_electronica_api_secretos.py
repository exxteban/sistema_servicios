"""Carga del certificado y el CSC en la API desde la pantalla de configuración."""
import base64
import io
from unittest.mock import patch

from werkzeug.datastructures import FileStorage

from app import db
from facturacion_electronica.models import FacturacionElectronicaConfig
from facturacion_electronica.services.proveedores.api_secretos import (
    MAX_CERTIFICADO_BYTES,
    subir_certificado,
    subir_csc,
)
from test_facturacion_electronica_proveedor_base import BaseProveedorApi

SOLICITAR = 'facturacion_electronica.services.proveedores.api_client.solicitar'


def _archivo(contenido=b'p12-falso', nombre='firma.p12'):
    return FileStorage(stream=io.BytesIO(contenido), filename=nombre)


class TestSubirSecretosApi(BaseProveedorApi):
    def _admin_client(self):
        from app.models import Usuario

        admin = Usuario.query.filter_by(username='admin').first()
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin.id_usuario)
            sess['_fresh'] = True
        return client

    def test_el_certificado_viaja_en_base64_y_no_se_guarda_local(self):
        config = self._activar_api()
        llamadas = []

        def _solicitar(cfg, metodo, ruta, json=None, **kwargs):
            llamadas.append((metodo, ruta, json))
            return {'certificate': {'ruc_in_cert': '80178105', 'not_after': '2027-09-15T00:00:00Z'}}, None

        with patch(SOLICITAR, _solicitar):
            resumen, error = subir_certificado(config, _archivo(), 'clave')

        self.assertIsNone(error)
        self.assertIn('80178105', resumen)
        self.assertIn('2027-09-15', resumen)
        metodo, ruta, cuerpo = llamadas[0]
        self.assertEqual((metodo, ruta), ('PUT', '/sifen/me/certificate/'))
        self.assertEqual(base64.b64decode(cuerpo['p12_base64']), b'p12-falso')
        self.assertEqual(cuerpo['password'], 'clave')

        guardado = FacturacionElectronicaConfig.obtener()
        self.assertFalse(guardado.cert_path)
        self.assertFalse(guardado.cert_password)

    def test_certificado_invalido_no_llega_a_la_api(self):
        config = self._activar_api()
        with patch(SOLICITAR, side_effect=AssertionError('no debe llamar')):
            _r, error = subir_certificado(config, _archivo(nombre='firma.pem'), 'x')
            self.assertIn('.p12', error)
            _r, error = subir_certificado(config, _archivo(b''), 'x')
            self.assertIn('vacío', error)
            grande = b'x' * (MAX_CERTIFICADO_BYTES + 1)
            _r, error = subir_certificado(config, _archivo(grande), 'x')
            self.assertIn('64 KB', error)

    def test_el_rechazo_de_la_api_se_muestra(self):
        config = self._activar_api()
        with patch(SOLICITAR, return_value=(None, 'La API respondió 422: Contraseña incorrecta')):
            _r, error = subir_certificado(config, _archivo(), 'mala')
        self.assertIn('Contraseña incorrecta', error)

    def test_csc_valida_el_id_y_lo_manda(self):
        config = self._activar_api()
        with patch(SOLICITAR, side_effect=AssertionError('no debe llamar')):
            _r, error = subir_csc(config, '12', 'ABCD')
        self.assertIn('4 dígitos', error)

        with patch(SOLICITAR, return_value=({'detail': 'CSC actualizado.'}, None)) as mock:
            resumen, error = subir_csc(config, '0001', ' ABCD ')
        self.assertIsNone(error)
        self.assertIn('CSC', resumen)
        self.assertEqual(mock.call_args.kwargs['json'], {'csc_id': '0001', 'csc': 'ABCD'})

    def test_la_ruta_sube_el_certificado(self):
        self._activar_api()
        with patch(SOLICITAR, return_value=({'certificate': {}}, None)) as mock:
            respuesta = self._admin_client().post(
                '/facturacion-electronica/proveedor/certificado',
                data={'certificado': (io.BytesIO(b'p12'), 'firma.p12'), 'cert_password': 'clave'},
                content_type='multipart/form-data',
            )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(mock.call_count, 1)

    def test_la_pantalla_muestra_la_carga_solo_en_modo_api(self):
        client = self._admin_client()
        html = client.get('/facturacion-electronica/configuracion').get_data(as_text=True)
        self.assertNotIn('Subir certificado a la API', html)

        self._activar_api()
        with patch(SOLICITAR, return_value=(None, 'sin red en la prueba')):
            html = client.get('/facturacion-electronica/configuracion').get_data(as_text=True)
        self.assertIn('Subir certificado a la API', html)
        self.assertIn('Subir CSC a la API', html)
        self.assertIn('Cargar timbrado en la API', html)

    def test_con_motor_propio_la_ruta_no_manda_nada(self):
        config = FacturacionElectronicaConfig.obtener()
        config.proveedor = 'propio'
        db.session.commit()
        with patch(SOLICITAR, side_effect=AssertionError('no debe llamar')):
            respuesta = self._admin_client().post(
                '/facturacion-electronica/proveedor/csc', data={'csc_id': '0001', 'csc': 'X'},
            )
        self.assertEqual(respuesta.status_code, 302)
