import re

from app import create_app, db
from app.models import Cliente, Configuracion, Rol, Usuario
from gastronomia.models import GastronomiaClienteConfig


def _loguear(client, app, username: str):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        assert usuario is not None
        user_id = usuario.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def _csrf(html: str) -> str:
    match = re.search(r'id="csrf-token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _crear_cliente_usuario(app, username: str, rol_nombre: str, *, gastronomia_activa: bool = True):
    with app.app_context():
        rol = Rol.query.filter_by(nombre=rol_nombre).first()
        assert rol is not None
        cliente = Cliente(nombre=f'Cliente {username}', ruc_ci=username, tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(
            id_cliente=cliente.id_cliente,
            username=username,
            nombre_completo=f'Usuario {username}',
            id_rol=rol.id_rol,
            activo=True,
        )
        usuario.set_password('clave123')
        db.session.add_all([
            usuario,
            GastronomiaClienteConfig(
                cliente_id=cliente.id_cliente,
                modo_operacion='gastronomia' if gastronomia_activa else 'servicios',
                gastronomia_activo=gastronomia_activa,
            ),
        ])
        db.session.commit()
        return cliente.id_cliente


def _crear_usuario_sin_cliente(app, username: str, rol_nombre: str):
    with app.app_context():
        rol = Rol.query.filter_by(nombre=rol_nombre).first()
        assert rol is not None
        usuario = Usuario(
            id_cliente=None,
            username=username,
            nombre_completo=f'Usuario {username}',
            id_rol=rol.id_rol,
            activo=True,
        )
        usuario.set_password('clave123')
        db.session.add(usuario)
        db.session.commit()
        return usuario.id_usuario


def test_rol_cocina_solo_ve_y_opera_cocina():
    app = create_app('testing')
    client = app.test_client()
    _crear_cliente_usuario(app, 'cocina_permiso', 'Cocina')
    _loguear(client, app, 'cocina_permiso')

    dashboard = client.get('/gastronomia/')
    assert dashboard.status_code == 200
    html = dashboard.get_data(as_text=True)
    assert 'Cocina' in html
    assert 'Categorias, productos y disponibilidad.' not in html
    assert 'Cobro y cierre del flujo operativo.' not in html

    assert client.get('/gastronomia/cocina').status_code == 200
    assert client.get('/api/gastronomia/cocina/pedidos').status_code == 200
    assert client.get('/gastronomia/menu', follow_redirects=False).status_code in (302, 303)

    csrf = _csrf(client.get('/gastronomia/cocina').get_data(as_text=True))
    menu_resp = client.post(
        '/api/gastronomia/categorias',
        json={'nombre': 'No permitido'},
        headers={'X-CSRFToken': csrf},
    )
    assert menu_resp.status_code == 403
    assert menu_resp.get_json()['permiso_requerido'] == 'gastronomia_menu'


def test_roles_mozo_y_caja_tienen_accesos_operativos_separados():
    app = create_app('testing')
    mozo = app.test_client()
    caja = app.test_client()
    _crear_cliente_usuario(app, 'mozo_permiso', 'Mozo')
    _crear_cliente_usuario(app, 'caja_gastro_permiso', 'Caja Gastronomia')

    _loguear(mozo, app, 'mozo_permiso')
    assert mozo.get('/gastronomia/pos').status_code == 200
    assert mozo.get('/gastronomia/salon').status_code == 200
    assert mozo.get('/gastronomia/caja', follow_redirects=False).status_code in (302, 303)

    _loguear(caja, app, 'caja_gastro_permiso')
    assert caja.get('/gastronomia/caja').status_code == 200
    assert caja.get('/api/gastronomia/caja/pedidos').status_code == 200
    assert caja.get('/gastronomia/menu', follow_redirects=False).status_code in (302, 303)
    assert caja.get('/api/gastronomia/reportes/resumen').status_code == 403


def test_dashboard_gastronomia_guarda_orden_manual_de_tarjetas():
    app = create_app('testing')
    client = app.test_client()
    _crear_cliente_usuario(app, 'admin_orden_dashboard', 'Administrador')
    _loguear(client, app, 'admin_orden_dashboard')

    dashboard = client.get('/gastronomia/')
    assert dashboard.status_code == 200
    csrf = _csrf(dashboard.get_data(as_text=True))

    response = client.put(
        '/api/gastronomia/dashboard/orden',
        json={'cards': ['caja', 'cocina', 'pos']},
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['cards'][:3] == ['caja', 'cocina', 'pos']

    dashboard_reordenado = client.get('/gastronomia/').get_data(as_text=True)
    caja_index = dashboard_reordenado.index('data-dashboard-card-id="caja"')
    pos_index = dashboard_reordenado.index('data-dashboard-card-id="pos"')
    assert caja_index < pos_index


def test_cajero_sin_cliente_usa_contexto_operativo_unico():
    app = create_app('testing')
    client = app.test_client()
    _crear_cliente_usuario(app, 'negocio_unico_gastro', 'Administrador')
    _crear_usuario_sin_cliente(app, 'cajero_sin_cliente', 'Cajero')

    _loguear(client, app, 'cajero_sin_cliente')

    dashboard = client.get('/gastronomia/')
    assert dashboard.status_code == 200
    html = dashboard.get_data(as_text=True)
    assert 'Este usuario no tiene un contexto operativo asignado' not in html
    assert 'Categorias, productos y disponibilidad.' not in html
    assert 'Cobro y cierre del flujo operativo.' in html

    assert client.get('/gastronomia/pos').status_code == 200
    assert client.get('/gastronomia/caja').status_code == 200
    assert client.get('/gastronomia/menu', follow_redirects=False).status_code in (302, 303)
    assert client.get('/gastronomia/cocina', follow_redirects=False).status_code in (302, 303)
    assert client.get('/gastronomia/salon', follow_redirects=False).status_code in (302, 303)
    assert client.get('/gastronomia/reportes', follow_redirects=False).status_code in (302, 303)


def test_admin_sin_cliente_usa_cliente_gastronomico_activo_unico():
    app = create_app('testing')
    client = app.test_client()
    _crear_cliente_usuario(app, 'resto_demo_activo', 'Administrador', gastronomia_activa=True)
    _crear_cliente_usuario(app, 'resto_demo_servicios', 'Administrador', gastronomia_activa=False)
    _crear_usuario_sin_cliente(app, 'admin_gastro_demo', 'Administrador')
    with app.app_context():
        Configuracion.establecer('modo_operacion_principal', 'gastronomia')

    _loguear(client, app, 'admin_gastro_demo')

    dashboard = client.get('/gastronomia/')
    assert dashboard.status_code == 200
    html = dashboard.get_data(as_text=True)
    assert 'Este usuario no tiene un contexto operativo asignado' not in html

    assert client.get('/gastronomia/menu').status_code == 200
    assert client.get('/gastronomia/pos').status_code == 200
