from flask import Flask

from facturacion_electronica.services.crypto import cifrar, descifrar


def _app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-secret-key'
    return app


def test_cifrar_descifrar_roundtrip():
    with _app().app_context():
        token = cifrar('miClave-123')
        assert token.startswith('fe1:')
        assert token != 'miClave-123'
        assert descifrar(token) == 'miClave-123'


def test_descifrar_valor_plano_legado():
    with _app().app_context():
        assert descifrar('passViejaEnPlano') == 'passViejaEnPlano'
        assert descifrar('') == ''
        assert descifrar(None) is None


def test_cifrar_vacio_no_rompe():
    with _app().app_context():
        assert cifrar('') == ''
        assert cifrar(None) is None
