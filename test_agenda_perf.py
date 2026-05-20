import unittest

from app import create_app, db
from app.models import Usuario
from app.utils.init_db import inicializar_datos_base


class TestAgendaPerfHeaders(unittest.TestCase):
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

    def _warm_and_get(self, path):
        self.client.get(path)
        return self.client.get(path)

    def test_dashboard_expone_server_timing_y_baja_cantidad_de_queries(self):
        response = self._warm_and_get('/agenda/dashboard')

        self.assertEqual(response.status_code, 200)
        self.assertIn('total;dur=', response.headers.get('Server-Timing', ''))
        self.assertIn('db;dur=', response.headers.get('Server-Timing', ''))
        self.assertIn('agenda-dashboard-counts;dur=', response.headers.get('Server-Timing', ''))
        self.assertIn('agenda-dashboard-priorities;dur=', response.headers.get('Server-Timing', ''))
        self.assertLessEqual(int(response.headers.get('X-DB-Query-Count', '999')), 8)

    def test_lista_mantiene_presupuesto_de_queries_bajo(self):
        response = self._warm_and_get('/agenda/actividades')

        self.assertEqual(response.status_code, 200)
        self.assertIn('total;dur=', response.headers.get('Server-Timing', ''))
        self.assertIn('db;dur=', response.headers.get('Server-Timing', ''))
        self.assertLessEqual(int(response.headers.get('X-DB-Query-Count', '999')), 10)


if __name__ == '__main__':
    unittest.main()
