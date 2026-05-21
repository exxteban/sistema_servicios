import unittest

from app import create_app, db
from app.models import Configuracion, Usuario
from app.utils.init_db import inicializar_datos_base


class TestAgendaPeluqueriaTurnoRapido(unittest.TestCase):
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

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()

    def test_renderiza_turno_rapido_peluqueria(self):
        response = self.client.get('/agenda/turnos/peluqueria/nuevo')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Nuevo turno rápido', html)
        self.assertIn('/agenda/actividades/nueva', html)
        self.assertIn('Corte + barba', html)

    def test_dashboard_peluqueria_apunta_al_turno_rapido(self):
        Configuracion.establecer('dashboard_negocio_activo', 'peluqueria_barberia')

        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('/agenda/turnos/peluqueria/nuevo', html)


if __name__ == '__main__':
    unittest.main()
