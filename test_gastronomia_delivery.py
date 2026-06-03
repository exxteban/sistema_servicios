import re

from app import create_app, db
from app.models import Cliente, Usuario
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaDeliveryUbicacion,
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


def _crear_contexto(app, suffix: str = ''):
    with app.app_context():
        cliente = Cliente(nombre=f'Resto Delivery Ruta{suffix}', ruc_ci=f'delivery_ruta{suffix}', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        admin = Usuario(
            id_cliente=cliente.id_cliente,
            username=f'admin_delivery_ruta{suffix}',
            nombre_completo='Admin Delivery Ruta',
            id_rol=1,
            activo=True,
        )
        delivery = Usuario(
            id_cliente=cliente.id_cliente,
            username=f'repartidor_delivery_ruta{suffix}',
            nombre_completo='Repartidor Delivery Ruta',
            id_rol=1,
            activo=True,
        )
        admin.set_password('clave123')
        delivery.set_password('clave123')
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Delivery')
        db.session.add_all([
            admin,
            delivery,
            categoria,
            GastronomiaClienteConfig(
                cliente_id=cliente.id_cliente,
                modo_operacion='gastronomia',
                gastronomia_activo=True,
            ),
        ])
        db.session.flush()
        producto = GastronomiaProducto(cliente_id=cliente.id_cliente, categoria_id=categoria.id_categoria, nombre='Pizza', precio=45000)
        db.session.add(producto)
        db.session.commit()
        return cliente.id_cliente, producto.id_producto, delivery.id_usuario


def test_delivery_registra_repartidor_asigna_y_repartidor_entrega():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id, delivery_user_id = _crear_contexto(app)
    _loguear(client, app, 'admin_delivery_ruta')

    csrf = _csrf(client.get('/gastronomia/delivery').get_data(as_text=True))
    repartidor_resp = client.post(
        '/api/gastronomia/delivery/repartidores',
        json={'nombre': 'Moto Uno', 'celular': '0981000001', 'usuario_id': delivery_user_id},
        headers={'X-CSRFToken': csrf},
    )
    assert repartidor_resp.status_code == 201
    repartidor_id = repartidor_resp.get_json()['repartidor']['id_repartidor']

    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'delivery',
            'referencia_entrega': 'Laura',
            'celular_cliente': '0981123456',
            'direccion_entrega': 'Calle 1',
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido_resp.status_code == 201
    pedido_id = pedido_resp.get_json()['pedido']['id_pedido']
    assert client.post(f'/api/gastronomia/pedidos/{pedido_id}/enviar-cocina', json={}, headers={'X-CSRFToken': csrf}).status_code == 200
    assert client.post(f'/api/gastronomia/cocina/pedidos/{pedido_id}/listo', json={}, headers={'X-CSRFToken': csrf}).status_code == 200

    asignar_resp = client.post(
        f'/api/gastronomia/delivery/pedidos/{pedido_id}/repartidor',
        json={'repartidor_id': repartidor_id},
        headers={'X-CSRFToken': csrf},
    )
    assert asignar_resp.status_code == 200
    assert asignar_resp.get_json()['pedido']['repartidor']['nombre'] == 'Moto Uno'

    _loguear(client, app, 'repartidor_delivery_ruta')
    csrf_ruta = _csrf(client.get('/gastronomia/delivery/ruta').get_data(as_text=True))
    ruta_resp = client.get('/api/gastronomia/delivery/ruta')
    assert ruta_resp.status_code == 200
    assert [pedido['id_pedido'] for pedido in ruta_resp.get_json()['pedidos']] == [pedido_id]

    salir_resp = client.post(
        f'/api/gastronomia/delivery/ruta/pedidos/{pedido_id}/salir',
        json={},
        headers={'X-CSRFToken': csrf_ruta},
    )
    assert salir_resp.status_code == 200
    assert salir_resp.get_json()['pedido']['estado'] == 'en_camino'

    ubicacion_resp = client.post(
        f'/api/gastronomia/delivery/ruta/pedidos/{pedido_id}/ubicacion',
        json={'latitud': -25.3001, 'longitud': -57.6359, 'precision_metros': 12},
        headers={'X-CSRFToken': csrf_ruta},
    )
    assert ubicacion_resp.status_code == 200
    assert ubicacion_resp.get_json()['ubicacion']['pedido_id'] == pedido_id

    entregar_resp = client.post(
        f'/api/gastronomia/delivery/ruta/pedidos/{pedido_id}/entregar',
        json={},
        headers={'X-CSRFToken': csrf_ruta},
    )
    assert entregar_resp.status_code == 200
    assert entregar_resp.get_json()['pedido']['estado'] == 'entregado'
    assert client.get('/api/gastronomia/delivery/ruta').get_json()['pedidos'] == []

    with app.app_context():
        eventos = GastronomiaPedidoEvento.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).order_by(
            GastronomiaPedidoEvento.id_evento.asc()
        ).all()
        assert 'pedido_repartidor_asignado' in [evento.tipo for evento in eventos]
        assert eventos[-1].tipo == 'pedido_entregado'
        ubicacion = GastronomiaDeliveryUbicacion.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).one()
        assert ubicacion.latitud == -25.3001


def test_delivery_ruta_operativa_muestra_pedidos_sin_repartidor_vinculado():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id, _delivery_user_id = _crear_contexto(app, '_operativa')
    _loguear(client, app, 'admin_delivery_ruta_operativa')

    csrf = _csrf(client.get('/gastronomia/delivery').get_data(as_text=True))
    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'delivery',
            'referencia_entrega': 'Laura',
            'celular_cliente': '0981123456',
            'direccion_entrega': 'Calle 1',
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido_resp.status_code == 201
    pedido_id = pedido_resp.get_json()['pedido']['id_pedido']
    assert client.post(f'/api/gastronomia/pedidos/{pedido_id}/enviar-cocina', json={}, headers={'X-CSRFToken': csrf}).status_code == 200
    assert client.post(f'/api/gastronomia/cocina/pedidos/{pedido_id}/listo', json={}, headers={'X-CSRFToken': csrf}).status_code == 200

    ruta_resp = client.get('/api/gastronomia/delivery/ruta')
    assert ruta_resp.status_code == 200
    ruta_data = ruta_resp.get_json()
    assert ruta_data['modo'] == 'operativo'
    assert [pedido['id_pedido'] for pedido in ruta_data['pedidos']] == [pedido_id]

    csrf_ruta = _csrf(client.get('/gastronomia/delivery/ruta').get_data(as_text=True))
    salir_resp = client.post(
        f'/api/gastronomia/delivery/ruta/pedidos/{pedido_id}/salir',
        json={},
        headers={'X-CSRFToken': csrf_ruta},
    )
    assert salir_resp.status_code == 200
    assert salir_resp.get_json()['pedido']['estado'] == 'en_camino'
