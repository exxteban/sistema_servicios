import re

from app import create_app, db
from app.models import Cliente, Usuario
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaPedido,
    GastronomiaPedidoEvento,
    GastronomiaPedidoPago,
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


def _crear_producto(app, nombre_cliente: str, username: str):
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
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Caja')
        db.session.add_all([
            usuario,
            categoria,
            GastronomiaClienteConfig(
                cliente_id=cliente.id_cliente,
                modo_operacion='gastronomia',
                gastronomia_activo=True,
            ),
        ])
        db.session.flush()
        producto = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Menu ejecutivo',
            precio=30000,
        )
        db.session.add(producto)
        db.session.commit()
        return cliente.id_cliente, producto.id_producto


def _crear_pedido_listo(client, csrf, producto_id):
    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_id, 'cantidad': 1}]},
        headers={'X-CSRFToken': csrf},
    )
    assert pedido_resp.status_code == 201
    pedido_id = pedido_resp.get_json()['pedido']['id_pedido']
    estado_resp = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/estado',
        json={'estado': 'listo'},
        headers={'X-CSRFToken': csrf},
    )
    assert estado_resp.status_code == 200
    return pedido_id


def test_caja_lista_y_cobra_pedido_con_descuento():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Caja', 'resto_caja')
    _loguear(client, app, 'resto_caja')

    page = client.get('/gastronomia/caja')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Caja' in html
    csrf = _csrf(html)
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)

    listado_resp = client.get('/api/gastronomia/caja/pedidos')
    assert listado_resp.status_code == 200
    assert [pedido['id_pedido'] for pedido in listado_resp.get_json()['pedidos']] == [pedido_id]

    cobrar_resp = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo', 'descuento_monto': 5000, 'observacion': 'Promo almuerzo'},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200
    pedido = cobrar_resp.get_json()['pedido']
    assert pedido['estado'] == 'cobrado'
    assert pedido['pago']['total_cobrado'] == 25000
    assert pedido['pago']['descuento_monto'] == 5000

    with app.app_context():
        pago = GastronomiaPedidoPago.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).first()
        assert pago is not None
        assert float(pago.total_cobrado) == 25000
        evento = GastronomiaPedidoEvento.query.filter_by(
            cliente_id=cliente_id,
            pedido_id=pedido_id,
            tipo='pedido_cobrado',
        ).first()
        assert evento is not None

    assert client.get('/api/gastronomia/caja/pedidos').get_json()['pedidos'] == []


def test_caja_no_cobra_pedido_ajeno_ni_reabre_cobrado():
    app = create_app('testing')
    client_uno = app.test_client()
    client_dos = app.test_client()
    _cliente_uno_id, producto_uno_id = _crear_producto(app, 'Resto Uno Caja', 'resto_uno_caja')
    _cliente_dos_id, producto_dos_id = _crear_producto(app, 'Resto Dos Caja', 'resto_dos_caja')

    _loguear(client_uno, app, 'resto_uno_caja')
    csrf_uno = _csrf(client_uno.get('/gastronomia/caja').get_data(as_text=True))
    pedido_uno_id = _crear_pedido_listo(client_uno, csrf_uno, producto_uno_id)

    _loguear(client_dos, app, 'resto_dos_caja')
    csrf_dos = _csrf(client_dos.get('/gastronomia/caja').get_data(as_text=True))
    pedido_dos_id = _crear_pedido_listo(client_dos, csrf_dos, producto_dos_id)

    ajeno_resp = client_dos.post(
        f'/api/gastronomia/caja/pedidos/{pedido_uno_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf_dos},
    )
    assert ajeno_resp.status_code == 404

    cobrar_resp = client_dos.post(
        f'/api/gastronomia/caja/pedidos/{pedido_dos_id}/cobrar',
        json={'metodo_pago': 'tarjeta'},
        headers={'X-CSRFToken': csrf_dos},
    )
    assert cobrar_resp.status_code == 200

    reabrir_resp = client_dos.post(
        f'/api/gastronomia/pedidos/{pedido_dos_id}/estado',
        json={'estado': 'listo'},
        headers={'X-CSRFToken': csrf_dos},
    )
    assert reabrir_resp.status_code == 400
    with app.app_context():
        pedido = GastronomiaPedido.query.get(pedido_dos_id)
        assert pedido.estado == 'cobrado'
