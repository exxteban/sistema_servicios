import unittest
from unittest.mock import patch

from app import create_app
from app.routes.tienda_bot_api import BOT_RATE_STATE
from test_tienda_bot_api import _ensure_store


class TestTiendaBotRateLimit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app('testing')
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def setUp(self):
        self.client = self.app.test_client()
        BOT_RATE_STATE.clear()

    def test_rate_limit_crear_sesion_devuelve_429(self):
        config = _ensure_store(slug='bot-rate-limit-session')
        with patch('app.routes.tienda_bot_api._is_bot_rate_limited', return_value=(True, 60)):
            response = self.client.post(f'/api/tienda/{config.slug}/bot/session', json={'origen': 'tienda_widget'})

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.get_json()['error'], 'demasiadas_solicitudes')
        self.assertEqual(response.headers.get('Retry-After'), '60')

    def test_rate_limit_mensajes_devuelve_429(self):
        config = _ensure_store(slug='bot-rate-limit-message')
        session_response = self.client.post(f'/api/tienda/{config.slug}/bot/session', json={'origen': 'tienda_widget'})
        token = session_response.get_json()['session_token']

        with patch('app.routes.tienda_bot_api._is_bot_rate_limited', return_value=(True, 45)):
            response = self.client.post(
                f'/api/tienda/{config.slug}/bot/session/{token}/messages',
                json={'mensaje': 'Hola'},
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.get_json()['error'], 'demasiadas_solicitudes')
        self.assertEqual(response.headers.get('Retry-After'), '45')


if __name__ == '__main__':
    unittest.main()
