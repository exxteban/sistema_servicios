import re
from datetime import timedelta

from app import create_app, db
from app.models import Cliente, Usuario
from app.utils.helpers import today_local, utc_bounds_for_local_dates
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaPedido,
    GastronomiaProducto,
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
    match = re.search(r'id="csrf-token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _crear_base(app, nombre_cliente: str, username: str, slug: str):
    with app.app_context():
        cliente = Cliente(nombre=nombre_cliente, ruc_ci=username, tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(
            id_cliente=cliente.id_cliente,
            username=username,
            nombre_completo=f'Admin {nombre_cliente}',
            id_rol=1,
            activo=True,
        )
        usuario.set_password('clave123')
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Minutas', orden=1)
        config = GastronomiaClienteConfig(
            cliente_id=cliente.id_cliente,
            modo_operacion='gastronomia',
            gastronomia_activo=True,
            menu_tv_slug=slug,
            menu_tv_publico_activo=True,
        )
        db.session.add_all([usuario, categoria, config])
        db.session.flush()
        producto = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Milanesa',
            precio=25000,
            orden=1,
        )
        oculto = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Secreto',
            precio=1,
            visible=False,
        )
        agotado = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Empanada',
            precio=6000,
            disponible=False,
            orden=2,
        )
        db.session.add_all([producto, oculto, agotado])
        db.session.commit()
        return cliente.id_cliente, producto.id_producto, agotado.id_producto


def _crear_pedido(client, csrf, producto_id, referencia='Ana'):
    response = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mostrador',
            'referencia_entrega': referencia,
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 201
    return response.get_json()['pedido']['id_pedido']


def _entregar(client, csrf, pedido_id):
    listo = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/estado',
        json={'estado': 'listo'},
        headers={'X-CSRFToken': csrf},
    )
    assert listo.status_code == 200
    entregado = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/estado',
        json={'estado': 'entregado'},
        headers={'X-CSRFToken': csrf},
    )
    assert entregado.status_code == 200


def test_entregas_filtra_por_fecha_entrega_busqueda_y_cliente():
    app = create_app('testing')
    client_uno = app.test_client()
    client_dos = app.test_client()
    _cliente_uno_id, producto_uno_id, _agotado_uno_id = _crear_base(app, 'Resto Entregas Uno', 'entregas_uno', 'entregas-uno')
    _cliente_dos_id, producto_dos_id, _agotado_dos_id = _crear_base(app, 'Resto Entregas Dos', 'entregas_dos', 'entregas-dos')

    _loguear(client_uno, app, 'entregas_uno')
    csrf_uno = _csrf(client_uno.get('/gastronomia/pos').get_data(as_text=True))
    pedido_hoy = _crear_pedido(client_uno, csrf_uno, producto_uno_id, 'Ana Retiro')
    _entregar(client_uno, csrf_uno, pedido_hoy)
    pedido_abierto = _crear_pedido(client_uno, csrf_uno, producto_uno_id, 'Sin entregar')
    pedido_ayer = _crear_pedido(client_uno, csrf_uno, producto_uno_id, 'Ayer')
    _entregar(client_uno, csrf_uno, pedido_ayer)

    with app.app_context():
        ayer = today_local() - timedelta(days=1)
        inicio_ayer, _fin_ayer = utc_bounds_for_local_dates(ayer, ayer)
        GastronomiaPedido.query.get(pedido_ayer).fecha_entrega = inicio_ayer + timedelta(hours=3)
        db.session.commit()

    response = client_uno.get('/api/gastronomia/entregas?fecha=hoy')
    assert response.status_code == 200
    data = response.get_json()
    ids = [pedido['id_pedido'] for pedido in data['pedidos']]
    assert ids == [pedido_hoy]
    assert pedido_abierto not in ids
    assert data['resumen']['cantidad_entregada'] == 1

    busqueda = client_uno.get('/api/gastronomia/entregas?fecha=hoy&q=Ana')
    assert [pedido['id_pedido'] for pedido in busqueda.get_json()['pedidos']] == [pedido_hoy]

    _loguear(client_dos, app, 'entregas_dos')
    csrf_dos = _csrf(client_dos.get('/gastronomia/pos').get_data(as_text=True))
    pedido_dos = _crear_pedido(client_dos, csrf_dos, producto_dos_id, 'Cliente Dos')
    _entregar(client_dos, csrf_dos, pedido_dos)
    listado_dos = client_dos.get('/api/gastronomia/entregas?fecha=hoy')
    assert [pedido['id_pedido'] for pedido in listado_dos.get_json()['pedidos']] == [pedido_dos]


def test_entregas_view_requiere_login():
    app = create_app('testing')
    client = app.test_client()
    response = client.get('/gastronomia/entregas')
    assert response.status_code in (302, 401)


def test_menu_tv_publico_respeta_visibilidad_disponibilidad_y_estado():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, _producto_id, _agotado_id = _crear_base(app, 'Resto TV', 'resto_tv', 'resto-tv')

    page = client.get('/gastronomia/menu-tv/resto-tv')
    assert page.status_code == 200
    response = client.get('/api/gastronomia/public/menu-tv/resto-tv')
    assert response.status_code == 200
    productos = response.get_json()['categorias'][0]['productos']
    nombres = [producto['nombre'] for producto in productos]
    assert nombres == ['Milanesa']
    assert 'Secreto' not in nombres
    assert 'Empanada' not in nombres

    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).first()
        config.menu_tv_mostrar_agotados = True
        db.session.commit()
    con_agotados = client.get('/api/gastronomia/public/menu-tv/resto-tv')
    nombres = [producto['nombre'] for producto in con_agotados.get_json()['categorias'][0]['productos']]
    assert nombres == ['Milanesa', 'Empanada']

    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).first()
        config.menu_tv_publico_activo = False
        db.session.commit()
    assert client.get('/api/gastronomia/public/menu-tv/resto-tv').status_code == 404
    assert client.get('/gastronomia/menu-tv/resto-tv').status_code == 404
