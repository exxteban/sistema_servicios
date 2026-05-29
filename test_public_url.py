from app import create_app
from app.models import Configuracion
from app.utils.public_url import CLAVE_URL_PUBLICA_SISTEMA, build_public_url


def test_build_public_url_usa_configuracion_publica():
    app = create_app('testing')
    with app.app_context():
        Configuracion.establecer(CLAVE_URL_PUBLICA_SISTEMA, 'https://negocio.example.com/')
        with app.test_request_context('/'):
            url = build_public_url('seguimiento.ver_seguimiento', token='abc123')
    assert url == 'https://negocio.example.com/seguimiento/abc123'


def test_build_public_url_usa_forwarded_host_si_no_hay_configuracion():
    app = create_app('testing')
    with app.app_context():
        Configuracion.establecer(CLAVE_URL_PUBLICA_SISTEMA, '')
        with app.test_request_context(
            '/',
            headers={'X-Forwarded-Host': 'publico.example.com', 'X-Forwarded-Proto': 'https'},
        ):
            url = build_public_url('seguimiento.ver_seguimiento', token='abc123')
    assert url == 'https://publico.example.com/seguimiento/abc123'
