import re

from app import create_app, db
from app.models import Cliente, Usuario
from gastronomia.models import GastronomiaClienteConfig, GastronomiaCategoria, GastronomiaProducto


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


def _crear_restaurante(app, nombre: str, username: str):
    with app.app_context():
        cliente = Cliente(nombre=nombre, ruc_ci=username, tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(
            id_cliente=cliente.id_cliente,
            username=username,
            nombre_completo=f'Admin {nombre}',
            id_rol=1,
            activo=True,
        )
        usuario.set_password('clave123')
        db.session.add(usuario)
        db.session.add(GastronomiaClienteConfig(
            cliente_id=cliente.id_cliente,
            modo_operacion='gastronomia',
            gastronomia_activo=True,
        ))
        db.session.commit()
        return cliente.id_cliente


def test_api_menu_crea_categoria_y_producto_con_cliente_de_sesion():
    app = create_app('testing')
    client = app.test_client()
    cliente_id = _crear_restaurante(app, 'Resto Uno', 'resto_uno')
    _loguear(client, app, 'resto_uno')

    page = client.get('/gastronomia/menu')
    assert page.status_code == 200
    csrf = _csrf(page.get_data(as_text=True))

    categoria_resp = client.post(
        '/api/gastronomia/categorias',
        json={'nombre': 'Hamburguesas', 'descripcion': 'Linea principal', 'orden': 1},
        headers={'X-CSRFToken': csrf},
    )
    assert categoria_resp.status_code == 201
    categoria_id = categoria_resp.get_json()['categoria']['id_categoria']

    producto_resp = client.post(
        '/api/gastronomia/productos',
        json={
            'categoria_id': categoria_id,
            'nombre': 'Clasica',
            'descripcion': 'Pan, carne y queso',
            'precio': '12500.50',
            'disponible': True,
            'visible': True,
        },
        headers={'X-CSRFToken': csrf},
    )

    assert producto_resp.status_code == 201
    producto = producto_resp.get_json()['producto']
    assert producto['precio'] == 12500.5
    with app.app_context():
        assert GastronomiaCategoria.query.filter_by(cliente_id=cliente_id).count() == 1
        assert GastronomiaProducto.query.filter_by(cliente_id=cliente_id).count() == 1


def test_api_menu_no_filtra_datos_entre_clientes():
    app = create_app('testing')
    client_uno = app.test_client()
    client_dos = app.test_client()
    cliente_uno_id = _crear_restaurante(app, 'Resto Uno', 'resto_uno')
    cliente_dos_id = _crear_restaurante(app, 'Resto Dos', 'resto_dos')

    with app.app_context():
        categoria_uno = GastronomiaCategoria(cliente_id=cliente_uno_id, nombre='Pizzas')
        categoria_dos = GastronomiaCategoria(cliente_id=cliente_dos_id, nombre='Pastas')
        db.session.add_all([categoria_uno, categoria_dos])
        db.session.commit()
        categoria_uno_id = categoria_uno.id_categoria

    _loguear(client_dos, app, 'resto_dos')
    page_dos = client_dos.get('/gastronomia/menu')
    csrf_dos = _csrf(page_dos.get_data(as_text=True))

    listado = client_dos.get('/api/gastronomia/categorias')
    assert listado.status_code == 200
    nombres = [item['nombre'] for item in listado.get_json()['categorias']]
    assert nombres == ['Pastas']

    update_resp = client_dos.put(
        f'/api/gastronomia/categorias/{categoria_uno_id}',
        json={'nombre': 'Pizzas editadas'},
        headers={'X-CSRFToken': csrf_dos},
    )
    assert update_resp.status_code == 404

    _loguear(client_uno, app, 'resto_uno')
    listado_uno = client_uno.get('/api/gastronomia/categorias')
    assert [item['nombre'] for item in listado_uno.get_json()['categorias']] == ['Pizzas']
