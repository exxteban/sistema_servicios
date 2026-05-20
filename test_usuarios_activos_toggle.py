import re

from app import create_app, db
from app.models import Rol, Usuario


def _extraer_csrf(html):
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html or '')
    assert match is not None
    return match.group(1)


def _loguear_admin(client, app):
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        admin_id = admin.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(admin_id)
        session['_fresh'] = True


def _obtener_rol_secundario(admin):
    rol = Rol.query.filter(
        Rol.activo == True,
        Rol.id_rol != admin.id_rol,
    ).order_by(Rol.nivel_jerarquia.asc()).first()
    if rol:
        return rol

    nivel_admin = admin.rol.nivel_jerarquia if admin.rol else 1
    assert nivel_admin > 0
    rol = Rol(
        nombre='qa_usuarios_toggle',
        descripcion='Rol auxiliar para pruebas de usuarios',
        nivel_jerarquia=nivel_admin - 1,
        activo=True,
    )
    db.session.add(rol)
    db.session.commit()
    return rol


def _crear_usuario_prueba(app, username, activo):
    with app.app_context():
        existente = Usuario.query.filter_by(username=username).first()
        if existente:
            db.session.delete(existente)
            db.session.commit()

        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        rol = _obtener_rol_secundario(admin)
        usuario = Usuario(
            username=username,
            nombre_completo=f'Usuario {username}',
            id_rol=rol.id_rol,
            activo=activo,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.commit()
        return usuario.id_usuario


def test_listado_usuarios_muestra_activos_por_defecto_y_permuta_estado():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    _crear_usuario_prueba(app, 'usuario_activo_switch', True)
    _crear_usuario_prueba(app, 'usuario_inactivo_switch', False)

    response = client.get('/usuarios/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Mostrando usuarios activos.' in html
    assert 'usuario_activo_switch' in html
    assert 'usuario_inactivo_switch' not in html

    response = client.get('/usuarios/?estado=inactivos')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Mostrando usuarios desactivados.' in html
    assert 'usuario_inactivo_switch' in html
    assert 'usuario_activo_switch' not in html


def test_toggle_activo_desde_listado_mueve_usuario_a_desactivados():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    user_id = _crear_usuario_prueba(app, 'usuario_toggle_desactivar', True)

    response = client.get('/usuarios/')
    assert response.status_code == 200
    csrf = _extraer_csrf(response.get_data(as_text=True))

    response = client.post(
        f'/usuarios/{user_id}/toggle-activo',
        data={
            'csrf_token': csrf,
            'next': '/usuarios/',
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    with app.app_context():
        usuario = db.session.get(Usuario, user_id)
        assert usuario is not None
        assert usuario.activo is False

    response = client.get('/usuarios/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'usuario_toggle_desactivar' not in html

    response = client.get('/usuarios/?estado=inactivos')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'usuario_toggle_desactivar' in html
