from app import db
from flask import render_template_string

from app import create_app
from app.models import Configuracion, Rol, Usuario
from app.services.system_modules import (
    CLAVE_MODULO_CRM,
    CLAVE_MODULO_SERVICIO_TECNICO,
    CLAVE_MODULO_WHATSAPP,
)
from flujo_caja import CLAVE_MODULO_FLUJO_CAJA


def _loguear(client, app, username: str):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        assert usuario is not None
        user_id = usuario.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def test_modulos_sistema_es_root_only():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, app, 'admin')

    response = client.get('/usuarios/modulos-sistema')

    assert response.status_code == 403


def test_modulos_sistema_bloquea_usuario_con_rol_root_pero_no_root_real():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        rol_root = Rol.query.filter_by(nombre='Root').first()
        assert rol_root is not None
        usuario = Usuario(
            username='encargado_root',
            nombre_completo='Encargado Root',
            id_rol=rol_root.id_rol,
            activo=True,
        )
        usuario.set_password('clave123456')
        db.session.add(usuario)
        db.session.commit()

    _loguear(client, app, 'encargado_root')

    response = client.get('/usuarios/modulos-sistema')

    assert response.status_code == 403


def test_modulos_sistema_root_ve_toggle_de_flujo_caja():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, app, 'root')

    response = client.get('/usuarios/modulos-sistema')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Modulos del sistema' in html
    assert 'Flujo de caja estimado' in html
    assert 'id="flujo_caja_activo"' in html
    assert 'Servicio tecnico' in html
    assert 'id="servicio_tecnico_activo"' in html
    assert 'CRM WhatsApp' in html
    assert 'id="crm_activo"' in html
    assert '>WhatsApp<' in html
    assert 'id="whatsapp_activo"' in html


def test_runtime_expone_flag_y_root_para_sidebar():
    app = create_app('testing')

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_MODULO_FLUJO_CAJA, False)
        Configuracion.establecer_bool(CLAVE_MODULO_SERVICIO_TECNICO, False)
        Configuracion.establecer_bool(CLAVE_MODULO_WHATSAPP, False)
        Configuracion.establecer_bool(CLAVE_MODULO_CRM, False)
        with app.test_request_context('/'):
            html = render_template_string(
                '{{ 1 if modulo_flujo_caja_activo else 0 }}|{{ 1 if modulo_servicio_tecnico_activo else 0 }}|{{ 1 if modulo_whatsapp_activo else 0 }}|{{ 1 if modulo_crm_activo else 0 }}|{{ 1 if es_usuario_root_actual else 0 }}'
            )

    assert html == '0|0|0|0|0'


def test_sidebar_muestra_modulos_sistema_solo_para_root_y_oculta_flujo_desactivado():
    app = create_app('testing')
    client_root = app.test_client()
    client_admin = app.test_client()
    _loguear(client_root, app, 'root')
    _loguear(client_admin, app, 'admin')

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_MODULO_FLUJO_CAJA, False)
        Configuracion.establecer_bool(CLAVE_MODULO_SERVICIO_TECNICO, False)

    root_response = client_root.get('/')
    admin_response = client_admin.get('/')

    root_html = root_response.get_data(as_text=True)
    admin_html = admin_response.get_data(as_text=True)
    assert 'Módulos del sistema' in root_html
    assert 'data-tab-title="Flujo proyectado"' not in root_html
    assert 'data-tab-title="Servicio Técnico"' not in root_html
    assert 'Módulos del sistema' not in admin_html


def test_sidebar_oculta_modulos_sistema_a_usuario_con_rol_root_pero_no_root_real():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        rol_root = Rol.query.filter_by(nombre='Root').first()
        assert rol_root is not None
        usuario = Usuario(
            username='supervisor_root',
            nombre_completo='Supervisor Root',
            id_rol=rol_root.id_rol,
            activo=True,
        )
        usuario.set_password('clave123456')
        db.session.add(usuario)
        db.session.commit()

    _loguear(client, app, 'supervisor_root')

    response = client.get('/')

    html = response.get_data(as_text=True)
    assert 'Módulos del sistema' not in html


def test_flujo_caja_redirige_si_el_modulo_esta_desactivado():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, app, 'admin')

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_MODULO_FLUJO_CAJA, False)

    response = client.get('/flujo-caja/', follow_redirects=False)

    assert response.status_code in (302, 303)
    assert '/flujo-caja/' not in (response.headers.get('Location') or '')


def test_servicio_tecnico_redirige_si_el_modulo_esta_desactivado():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, app, 'admin')

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_MODULO_SERVICIO_TECNICO, False)

    response = client.get('/reparaciones/', follow_redirects=False)

    assert response.status_code in (302, 303)
    assert '/reparaciones/' not in (response.headers.get('Location') or '')


def test_whatsapp_redirige_si_el_modulo_esta_desactivado():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, app, 'admin')

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_MODULO_WHATSAPP, False)

    response = client.get('/whatsapp/panel', follow_redirects=False)

    assert response.status_code in (302, 303)
    assert '/whatsapp/panel' not in (response.headers.get('Location') or '')


def test_crm_redirige_si_el_modulo_esta_desactivado():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, app, 'admin')

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_MODULO_CRM, False)

    response = client.get('/crm/', follow_redirects=False)

    assert response.status_code in (302, 303)
    assert '/crm/' not in (response.headers.get('Location') or '')
