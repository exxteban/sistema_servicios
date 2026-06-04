import re

from app import create_app, db
from app.models import Cliente, Usuario
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaPedido,
    GastronomiaPedidoEvento,
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


def _assert_sin_importes(value):
    claves_importe = {
        'costo_envio', 'descuento_linea', 'descuento_monto', 'pago', 'precio',
        'precio_delta', 'precio_original', 'precio_unitario', 'subtotal', 'total',
        'total_cobrado',
    }
    if isinstance(value, list):
        for item in value:
            _assert_sin_importes(item)
    elif isinstance(value, dict):
        assert not claves_importe.intersection(value)
        for item in value.values():
            _assert_sin_importes(item)


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
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Cocina')
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
            nombre='Milanesa',
            precio=25000,
        )
        db.session.add(producto)
        db.session.commit()
        return cliente.id_cliente, producto.id_producto


def _crear_pedido_enviado(client, csrf, producto_id):
    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mostrador',
            'referencia_entrega': 'Juan mostrador',
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido_resp.status_code == 201
    pedido_id = pedido_resp.get_json()['pedido']['id_pedido']
    enviar_resp = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/enviar-cocina',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert enviar_resp.status_code == 200
    return pedido_id


def test_cocina_lista_pedidos_eventos_y_cambia_estados():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Uno', 'resto_uno')
    _loguear(client, app, 'resto_uno')

    page = client.get('/gastronomia/cocina')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Cocina' in html
    assert 'Delivery' in html
    csrf = _csrf(html)
    pedido_id = _crear_pedido_enviado(client, csrf, producto_id)

    cocina_resp = client.get('/api/gastronomia/cocina/pedidos')
    assert cocina_resp.status_code == 200
    pedidos = cocina_resp.get_json()['pedidos']
    assert [pedido['id_pedido'] for pedido in pedidos] == [pedido_id]
    assert [pedido['estado'] for pedido in pedidos] == ['enviado_cocina']
    assert pedidos[0]['codigo_entrega'] == f'#{pedido_id:03d}'
    assert pedidos[0]['referencia_entrega'] == 'Juan mostrador'
    _assert_sin_importes(pedidos)

    tomar_resp = client.post(
        f'/api/gastronomia/cocina/pedidos/{pedido_id}/tomar',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert tomar_resp.status_code == 200
    assert tomar_resp.get_json()['pedido']['estado'] == 'preparando'
    _assert_sin_importes(tomar_resp.get_json()['pedido'])
    eventos_resp = client.get('/api/gastronomia/cocina/eventos?after=0')
    assert eventos_resp.status_code == 200
    _assert_sin_importes(eventos_resp.get_json()['eventos'])
    cocina_resp = client.get('/api/gastronomia/cocina/pedidos')
    assert cocina_resp.status_code == 200
    pedidos = cocina_resp.get_json()['pedidos']
    assert [pedido['estado'] for pedido in pedidos] == ['preparando']

    listo_resp = client.post(
        f'/api/gastronomia/cocina/pedidos/{pedido_id}/listo',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert listo_resp.status_code == 200
    assert listo_resp.get_json()['pedido']['estado'] == 'listo'
    cocina_resp = client.get('/api/gastronomia/cocina/pedidos')
    assert cocina_resp.status_code == 200
    pedidos = cocina_resp.get_json()['pedidos']
    assert [pedido['estado'] for pedido in pedidos] == ['listo']

    entregar_resp = client.post(
        f'/api/gastronomia/cocina/pedidos/{pedido_id}/entregar',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert entregar_resp.status_code == 200
    assert entregar_resp.get_json()['pedido']['estado'] == 'entregado'
    cocina_resp = client.get('/api/gastronomia/cocina/pedidos')
    assert cocina_resp.status_code == 200
    assert cocina_resp.get_json()['pedidos'] == []

    with app.app_context():
        pedido = GastronomiaPedido.query.filter_by(cliente_id=cliente_id, id_pedido=pedido_id).first()
        assert pedido.fecha_inicio_preparacion is not None
        assert pedido.fecha_listo is not None
        assert pedido.fecha_entrega is not None
        eventos = GastronomiaPedidoEvento.query.filter_by(cliente_id=cliente_id).order_by(
            GastronomiaPedidoEvento.id_evento.asc()
        ).all()
        assert [evento.tipo for evento in eventos] == [
            'pedido_creado',
            'pedido_enviado_cocina',
            'pedido_preparando',
            'pedido_listo',
            'pedido_entregado',
        ]


def test_cocina_muestra_delivery_en_camino_y_lo_entrega():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id = _crear_producto(app, 'Resto Delivery Cocina', 'resto_delivery_cocina')
    _loguear(client, app, 'resto_delivery_cocina')

    page = client.get('/gastronomia/cocina')
    csrf = _csrf(page.get_data(as_text=True))
    delivery_page = client.get('/gastronomia/delivery')
    assert delivery_page.status_code == 200
    assert 'Cocina' in delivery_page.get_data(as_text=True)

    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'delivery',
            'referencia_entrega': 'Carla',
            'celular_cliente': '0981123456',
            'direccion_entrega': 'Av. Siempre Viva 742',
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido_resp.status_code == 201
    pedido_id = pedido_resp.get_json()['pedido']['id_pedido']
    assert client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/enviar-cocina',
        json={},
        headers={'X-CSRFToken': csrf},
    ).status_code == 200
    assert client.post(
        f'/api/gastronomia/cocina/pedidos/{pedido_id}/listo',
        json={},
        headers={'X-CSRFToken': csrf},
    ).status_code == 200
    salir_resp = client.post(
        f'/api/gastronomia/cocina/pedidos/{pedido_id}/salir',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert salir_resp.status_code == 200
    assert salir_resp.get_json()['pedido']['estado'] == 'en_camino'

    cocina_resp = client.get('/api/gastronomia/cocina/pedidos')
    assert cocina_resp.status_code == 200
    pedidos = cocina_resp.get_json()['pedidos']
    assert [pedido['id_pedido'] for pedido in pedidos] == [pedido_id]
    assert [pedido['estado'] for pedido in pedidos] == ['en_camino']

    entregar_resp = client.post(
        f'/api/gastronomia/cocina/pedidos/{pedido_id}/entregar',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert entregar_resp.status_code == 200
    assert entregar_resp.get_json()['pedido']['estado'] == 'entregado'
    assert client.get('/api/gastronomia/cocina/pedidos').get_json()['pedidos'] == []


def test_cocina_recibe_delivery_automaticamente_sin_envio_manual():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Delivery Automatico', 'resto_delivery_auto')
    _loguear(client, app, 'resto_delivery_auto')

    csrf = _csrf(client.get('/gastronomia/cocina').get_data(as_text=True))
    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'delivery',
            'referencia_entrega': 'Ana',
            'celular_cliente': '0981555111',
            'direccion_entrega': 'Centro 123',
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido_resp.status_code == 201
    pedido = pedido_resp.get_json()['pedido']
    assert pedido['estado'] == 'enviado_cocina'
    assert pedido['fecha_envio_cocina'] is not None

    cocina_resp = client.get('/api/gastronomia/cocina/pedidos')
    assert cocina_resp.status_code == 200
    pedidos = cocina_resp.get_json()['pedidos']
    assert [item['id_pedido'] for item in pedidos] == [pedido['id_pedido']]
    assert pedidos[0]['estado'] == 'enviado_cocina'

    with app.app_context():
        pedido_db = GastronomiaPedido.query.filter_by(cliente_id=cliente_id, id_pedido=pedido['id_pedido']).one()
        pedido_db.estado = 'abierto'
        pedido_db.fecha_envio_cocina = None
        db.session.commit()

    pedidos_legacy = client.get('/api/gastronomia/cocina/pedidos').get_json()['pedidos']
    assert [item['id_pedido'] for item in pedidos_legacy] == [pedido['id_pedido']]
    assert pedidos_legacy[0]['estado'] == 'enviado_cocina'


def test_cocina_no_muestra_eventos_de_otro_cliente():
    app = create_app('testing')
    client_uno = app.test_client()
    client_dos = app.test_client()
    _cliente_uno_id, producto_uno_id = _crear_producto(app, 'Resto Uno', 'resto_uno')
    _cliente_dos_id, producto_dos_id = _crear_producto(app, 'Resto Dos', 'resto_dos')

    _loguear(client_uno, app, 'resto_uno')
    csrf_uno = _csrf(client_uno.get('/gastronomia/cocina').get_data(as_text=True))
    pedido_uno_id = _crear_pedido_enviado(client_uno, csrf_uno, producto_uno_id)

    _loguear(client_dos, app, 'resto_dos')
    csrf_dos = _csrf(client_dos.get('/gastronomia/cocina').get_data(as_text=True))
    pedido_dos_id = _crear_pedido_enviado(client_dos, csrf_dos, producto_dos_id)

    eventos_dos = client_dos.get('/api/gastronomia/cocina/eventos').get_json()['eventos']
    assert {evento['pedido_id'] for evento in eventos_dos} == {pedido_dos_id}
    pedidos_dos = client_dos.get('/api/gastronomia/cocina/pedidos').get_json()['pedidos']
    assert [pedido['id_pedido'] for pedido in pedidos_dos] == [pedido_dos_id]
    assert pedido_uno_id not in {pedido['id_pedido'] for pedido in pedidos_dos}
