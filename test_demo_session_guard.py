from datetime import datetime, timedelta

from app import create_app, db
from app.models import Rol, Usuario
from app.services.demo_session_guard import (
    DEMO_BLOCKED_UNTIL_PREF,
    DEMO_LOGIN_STARTED_SESSION_KEY,
    format_demo_timestamp,
)


def _crear_usuario(app, username='demo'):
    with app.app_context():
        existente = Usuario.query.filter_by(username=username).first()
        if existente:
            db.session.delete(existente)
            db.session.commit()

        rol = Rol.query.first()
        if rol is None:
            rol = Rol(nombre='qa_demo', descripcion='Rol demo QA', nivel_jerarquia=1, activo=True)
            db.session.add(rol)
            db.session.commit()

        usuario = Usuario(
            username=username,
            nombre_completo=f'Usuario {username}',
            id_rol=rol.id_rol,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.commit()
        return usuario.id_usuario


def _login_por_sesion(client, user_id, started_at):
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True
        session[DEMO_LOGIN_STARTED_SESSION_KEY] = format_demo_timestamp(started_at)


def test_usuario_demo_expira_a_los_10_minutos_y_queda_bloqueado():
    app = create_app('testing')
    app.config['DEMO_SESSION_MINUTES'] = 10
    app.config['DEMO_BLOCK_MINUTES'] = 30
    client = app.test_client()
    user_id = _crear_usuario(app)

    _login_por_sesion(client, user_id, datetime.utcnow() - timedelta(minutes=11))

    response = client.get('/api/dashboard/totales')
    assert response.status_code == 403
    assert response.get_json()['error'] == 'demo_blocked'
    assert 'modo demo' in response.get_json()['mensaje']

    with app.app_context():
        usuario = db.session.get(Usuario, user_id)
        assert usuario.get_preferencia(DEMO_BLOCKED_UNTIL_PREF) is not None

    with client.session_transaction() as session:
        assert session.get('_user_id') is None


def test_usuario_demo_bloqueado_no_puede_volver_a_loguearse():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()
    user_id = _crear_usuario(app)

    with app.app_context():
        usuario = db.session.get(Usuario, user_id)
        usuario.set_preferencia(
            DEMO_BLOCKED_UNTIL_PREF,
            format_demo_timestamp(datetime.utcnow() + timedelta(minutes=20)),
        )
        db.session.commit()

    response = client.post(
        '/auth/login',
        data={'username': 'demo', 'password': '1234'},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert 'modo demo' in response.get_data(as_text=True)
    with client.session_transaction() as session:
        assert session.get('_user_id') is None


def test_usuario_no_demo_no_expira_por_guard_demo():
    app = create_app('testing')
    client = app.test_client()
    user_id = _crear_usuario(app, username='usuario_normal_demo_guard')

    _login_por_sesion(client, user_id, datetime.utcnow() - timedelta(minutes=60))

    response = client.get('/api/dashboard/totales')
    assert response.status_code != 403
    with client.session_transaction() as session:
        assert session.get('_user_id') == str(user_id)


def test_usuario_demo_no_puede_cambiar_password():
    app = create_app('testing')
    client = app.test_client()
    user_id = _crear_usuario(app)
    _login_por_sesion(client, user_id, datetime.utcnow())

    response = client.get('/auth/cambiar-password', follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers['Location'].endswith('/')
