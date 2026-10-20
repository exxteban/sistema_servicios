"""Quien no tiene permiso para Agenda (o CRM) recibe un 403 legible, no un error 500."""
import unittest

from app import create_app, db
from app.models import Rol, Usuario
from app.utils.init_db import inicializar_datos_base


class TestSinPermiso403(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        cls.ctx.pop()

    def setUp(self):
        db.session.remove()
        db.drop_all()
        db.create_all()
        inicializar_datos_base(config_name='testing')
        rol = Rol.query.filter_by(nombre='Auditoria').first()
        self.assertIsNotNone(rol)
        self.usuario = Usuario(username='auditor', nombre_completo='Auditor Test', id_rol=rol.id_rol, activo=True)
        self.usuario.set_password('1234')
        db.session.add(self.usuario)
        db.session.commit()
        self.assertFalse(self.usuario.tiene_permiso('agenda_acceso'))

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.usuario.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()

    def test_agenda_html_devuelve_403_con_mensaje(self):
        response = self.client.get('/agenda/actividades', headers={'Accept': 'text/html'})

        self.assertEqual(response.status_code, 403)
        html = response.get_data(as_text=True)
        self.assertIn('No tienes permiso para acceder a Agenda', html)
        self.assertIn('Volver al dashboard', html)

    def test_agenda_api_sigue_devolviendo_json(self):
        response = self.client.get('/agenda/api/peluqueria/ocupados', headers={'Accept': 'application/json'})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['permiso_requerido'], 'agenda_acceso')

    def test_crm_html_tambien_devuelve_403(self):
        response = self.client.get('/crm/', headers={'Accept': 'text/html'})

        self.assertIn(response.status_code, (403, 404))
        if response.status_code == 403:
            self.assertIn('No tienes permiso para acceder a CRM WhatsApp', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
