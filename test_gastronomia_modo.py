import re

from app import create_app, db
from app.models import Cliente, Configuracion, Usuario
from gastronomia.services.modo_operacion import (
    MODO_GASTRONOMIA,
    MODO_SERVICIOS,
    obtener_modo_operacion,
    obtener_modo_operacion_cliente,
)


def _loguear(client, app, username: str):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        assert usuario is not None
        user_id = usuario.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _crear_cliente_y_usuario(app):
    with app.app_context():
        cliente = Cliente(nombre='Restaurante Test', ruc_ci='9000', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(
            id_cliente=cliente.id_cliente,
            username='resto_admin',
            nombre_completo='Admin Restaurante',
            id_rol=1,
            activo=True,
        )
        usuario.set_password('clave123')
        db.session.add(usuario)
        db.session.commit()
        return cliente.id_cliente


def test_modo_gastronomia_default_es_servicios():
    app = create_app('testing')
    cliente_id = _crear_cliente_y_usuario(app)

    with app.app_context():
        assert obtener_modo_operacion_cliente(cliente_id) == MODO_SERVICIOS


def test_root_activa_gastronomia_global_desde_modulos():
    app = create_app('testing')
    client = app.test_client()
    _crear_cliente_y_usuario(app)
    _loguear(client, app, 'root')

    response = client.get('/usuarios/modulos-sistema')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Modo Gastronomia global' in html
    csrf = _csrf(html)

    post_response = client.post(
        '/usuarios/modulos-sistema/gastronomia-modo',
        data={
            'csrf_token': csrf,
            'modo_operacion': MODO_GASTRONOMIA,
        },
        follow_redirects=False,
    )

    assert post_response.status_code in (302, 303)
    with app.app_context():
        assert obtener_modo_operacion() == MODO_GASTRONOMIA
        assert Configuracion.obtener('modo_operacion_principal') == MODO_GASTRONOMIA


def test_dashboard_redirige_a_gastronomia_si_modo_global_activo():
    app = create_app('testing')
    client = app.test_client()
    _crear_cliente_y_usuario(app)

    with app.app_context():
        Configuracion.establecer('modo_operacion_principal', MODO_GASTRONOMIA)

    _loguear(client, app, 'resto_admin')

    response = client.get('/', follow_redirects=False)
    assert response.status_code in (302, 303)
    assert response.headers['Location'].endswith('/gastronomia/')

    gastronomia_response = client.get('/gastronomia/')
    assert gastronomia_response.status_code == 200
    html = gastronomia_response.get_data(as_text=True)
    assert 'Gastronomia' in html
    assert 'BI Gastronomia' in html
    assert '/inteligencia?vista=gastronomia' in html


def test_root_sin_cliente_usa_contexto_unico_en_gastronomia():
    app = create_app('testing')
    client = app.test_client()
    _crear_cliente_y_usuario(app)

    with app.app_context():
        Configuracion.establecer('modo_operacion_principal', MODO_GASTRONOMIA)

    _loguear(client, app, 'root')

    dashboard = client.get('/gastronomia/')
    assert dashboard.status_code == 200
    html = dashboard.get_data(as_text=True)
    assert 'Este usuario no tiene un contexto operativo asignado' not in html

    pos_response = client.get('/gastronomia/pos')
    assert pos_response.status_code == 200


def test_root_sin_negocio_operativo_bootstrapea_cliente_gastronomia():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer('modo_operacion_principal', MODO_GASTRONOMIA)

    _loguear(client, app, 'root')

    dashboard = client.get('/gastronomia/')
    assert dashboard.status_code == 200
    html = dashboard.get_data(as_text=True)
    assert 'Este usuario no tiene un contexto operativo asignado' not in html

    with app.app_context():
        clientes = (
            Cliente.query
            .filter(Cliente.activo.is_(True), Cliente.id_cliente != 1)
            .order_by(Cliente.id_cliente.asc())
            .all()
        )
        assert len(clientes) == 1
        cliente = clientes[0]
        assert cliente.nombre == 'Negocio principal'
        config = cliente.gastronomia_config
        assert config is not None
        assert config.gastronomia_activo is True
        assert config.modo_operacion == MODO_GASTRONOMIA
