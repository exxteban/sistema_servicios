from flask import render_template_string

from app import create_app, db
from app.models import Configuracion, Usuario
from cobranzas import CLAVE_COBRANZAS_ACTIVO, CLAVE_VENTAS_CREDITO_ACTIVO


def _loguear_admin(client, app):
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        admin_id = admin.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(admin_id)
        session['_fresh'] = True


def _loguear_root(client, app):
    with app.app_context():
        root = Usuario.query.filter_by(username='root').first()
        assert root is not None
        root_id = root.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(root_id)
        session['_fresh'] = True


def test_flags_cobranzas_y_credito_quedan_en_false_por_defecto():
    app = create_app('testing')

    with app.app_context():
        assert db.session.get(Configuracion, CLAVE_VENTAS_CREDITO_ACTIVO) is not None
        assert db.session.get(Configuracion, CLAVE_COBRANZAS_ACTIVO) is not None
        assert Configuracion.obtener_bool(CLAVE_VENTAS_CREDITO_ACTIVO, default=True) is False
        assert Configuracion.obtener_bool(CLAVE_COBRANZAS_ACTIVO, default=True) is False


def test_runtime_expone_flags_cobranzas_y_credito():
    app = create_app('testing')

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)
        Configuracion.establecer_bool(CLAVE_COBRANZAS_ACTIVO, True)

        with app.test_request_context('/'):
            html = render_template_string(
                '{{ 1 if ventas_credito_activo else 0 }}|{{ 1 if modulo_cobranzas_activo else 0 }}'
            )

        assert html == '1|1'


def test_ruta_cobranzas_redirige_al_dashboard_si_modulo_esta_apagado():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    response = client.get('/cobranzas/', follow_redirects=False)

    assert response.status_code in (302, 303)
    assert '/cobranzas/' not in (response.headers.get('Location') or '')


def test_ruta_cobranzas_renderiza_dashboard_si_modulo_esta_activo():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_COBRANZAS_ACTIVO, True)

    response = client.get('/cobranzas/', follow_redirects=False)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Cobranzas' in html
    assert 'Cuentas abiertas' in html
    assert 'Cuentas vencidas' in html


def test_configuracion_modulos_actualiza_flags_de_credito_y_cobranzas():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()
    _loguear_root(client, app)

    response = client.post(
        '/usuarios/modulos-sistema',
        data={
            'control_empleados_activo': '0',
            'ventas_credito_activo': '1',
            'cobranzas_activo': '1',
            'flujo_caja_activo': '1',
        },
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    with app.app_context():
        assert Configuracion.obtener_bool(CLAVE_VENTAS_CREDITO_ACTIVO, default=False) is True
        assert Configuracion.obtener_bool(CLAVE_COBRANZAS_ACTIVO, default=False) is True
