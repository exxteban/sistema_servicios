import unittest

from app import create_app, db


class TestDashboardServiciosProfesionalesUI(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

        from app.models import Configuracion, Usuario

        self.admin = Usuario.query.filter_by(username='admin').first()
        self.assertIsNotNone(self.admin)

        Configuracion.establecer('dashboard_negocio_activo', 'servicios')
        Configuracion.establecer('control_empleados_activo', '1')
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id_usuario)
            sess['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_dashboard_ancla_selector_y_no_envia_profesionales_a_empleados(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

        html = response.get_data(as_text=True)
        self.assertIn('class="absolute left-0 z-[9999] mt-2 w-[min(20rem,calc(100vw-6rem))]', html)
        self.assertIn('data-tab-title="Usuarios" data-tab-icon="fas fa-user-cog"', html)
        self.assertNotIn('data-tab-title="Profesionales" data-tab-icon="fas fa-users"', html)


if __name__ == '__main__':
    unittest.main()
