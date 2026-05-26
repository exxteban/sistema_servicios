import re

from app import create_app, db
from app.models import Caja, Cliente, ColaCobro, DetalleVenta, MetodoPago, MovimientoCaja, PagoVenta, SesionCaja, Usuario, Venta
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


def _abrir_caja(app, username: str):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        assert usuario is not None
        caja = Caja(nombre=f'Caja {username}', ubicacion='Gastronomia')
        db.session.add(caja)
        db.session.flush()
        sesion = SesionCaja(
            id_caja=caja.id_caja,
            id_usuario=usuario.id_usuario,
            monto_inicial=0,
            estado='abierta',
        )
        db.session.add(sesion)
        db.session.commit()
        return sesion.id_sesion


def _crear_pedido_listo(client, csrf, producto_id):
    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mostrador',
            'referencia_entrega': 'Ana retiro',
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
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


def _crear_pedido_abierto(client, csrf, producto_id, referencia_entrega=None):
    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mostrador',
            'referencia_entrega': referencia_entrega,
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido_resp.status_code == 201
    return pedido_resp.get_json()['pedido']['id_pedido']


def test_caja_lista_y_cobra_pedido_con_descuento():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Caja', 'resto_caja')
    _loguear(client, app, 'resto_caja')
    id_sesion = _abrir_caja(app, 'resto_caja')

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
    assert pedido['estado'] == 'listo'
    assert pedido['estado_pago'] == 'pagado'
    assert pedido['pago']['total_cobrado'] == 25000
    assert pedido['pago']['descuento_monto'] == 5000

    ticket_resp = client.get(f'/gastronomia/pedidos/{pedido_id}/ticket?preview=1')
    assert ticket_resp.status_code == 200
    ticket_html = ticket_resp.get_data(as_text=True)
    assert f'Ticket Pedido #{pedido_id}' in ticket_html
    assert f'#{pedido_id:03d}' in ticket_html
    assert 'Ana retiro' in ticket_html
    assert 'Menu ejecutivo' in ticket_html
    assert 'Efectivo' in ticket_html

    with app.app_context():
        pago = GastronomiaPedidoPago.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).first()
        assert pago is not None
        assert float(pago.total_cobrado) == 25000
        assert pago.id_sesion_caja == id_sesion
        assert pago.id_metodo_pago is not None
        assert pago.id_venta is not None
        assert pago.id_movimiento_caja is not None
        venta = Venta.query.get(pago.id_venta)
        assert venta is not None
        assert float(venta.subtotal) == 30000
        assert float(venta.descuento_monto) == 5000
        assert float(venta.total) == 25000
        assert DetalleVenta.query.filter_by(id_venta=venta.id_venta).count() == 1
        pago_venta = PagoVenta.query.filter_by(id_venta=venta.id_venta).first()
        assert pago_venta is not None
        assert float(pago_venta.monto) == 25000
        movimiento = MovimientoCaja.query.get(pago.id_movimiento_caja)
        assert movimiento is not None
        assert movimiento.id_sesion_caja == id_sesion
        assert movimiento.referencia_tipo == 'venta'
        assert movimiento.referencia_id == venta.id_venta
        evento = GastronomiaPedidoEvento.query.filter_by(
            cliente_id=cliente_id,
            pedido_id=pedido_id,
            tipo='pedido_cobrado',
        ).first()
        assert evento is not None

    assert client.get('/api/gastronomia/caja/pedidos').get_json()['pedidos'] == []


def test_caja_no_cobra_pedido_ajeno_ni_duplica_cobro():
    app = create_app('testing')
    client_uno = app.test_client()
    client_dos = app.test_client()
    _cliente_uno_id, producto_uno_id = _crear_producto(app, 'Resto Uno Caja', 'resto_uno_caja')
    _cliente_dos_id, producto_dos_id = _crear_producto(app, 'Resto Dos Caja', 'resto_dos_caja')

    _loguear(client_uno, app, 'resto_uno_caja')
    _abrir_caja(app, 'resto_uno_caja')
    csrf_uno = _csrf(client_uno.get('/gastronomia/caja').get_data(as_text=True))
    pedido_uno_id = _crear_pedido_listo(client_uno, csrf_uno, producto_uno_id)

    _loguear(client_dos, app, 'resto_dos_caja')
    _abrir_caja(app, 'resto_dos_caja')
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

    duplicado_resp = client_dos.post(
        f'/api/gastronomia/caja/pedidos/{pedido_dos_id}/cobrar',
        json={'metodo_pago': 'tarjeta'},
        headers={'X-CSRFToken': csrf_dos},
    )
    assert duplicado_resp.status_code == 400
    with app.app_context():
        pedido = GastronomiaPedido.query.get(pedido_dos_id)
        assert pedido.estado == 'listo'


def test_pedido_abierto_puede_cobrarse_y_luego_enviarse_a_cocina():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id = _crear_producto(app, 'Resto Prepago', 'resto_prepago')
    _loguear(client, app, 'resto_prepago')
    _abrir_caja(app, 'resto_prepago')

    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))
    pedido_id = _crear_pedido_abierto(client, csrf, producto_id)

    cobrar_resp = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200
    pedido_cobrado = cobrar_resp.get_json()['pedido']
    assert pedido_cobrado['estado'] == 'abierto'
    assert pedido_cobrado['estado_pago'] == 'pagado'

    enviar_resp = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/enviar-cocina',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert enviar_resp.status_code == 200
    assert enviar_resp.get_json()['pedido']['estado'] == 'enviado_cocina'
    assert enviar_resp.get_json()['pedido']['estado_pago'] == 'pagado'

    cocina_resp = client.get('/api/gastronomia/cocina/pedidos')
    assert cocina_resp.status_code == 200
    assert [pedido['id_pedido'] for pedido in cocina_resp.get_json()['pedidos']] == [pedido_id]


def test_cobro_avanzado_usa_checkout_central_y_envia_a_cocina():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Checkout', 'resto_checkout')
    _loguear(client, app, 'resto_checkout')
    _abrir_caja(app, 'resto_checkout')

    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))
    pedido_id = _crear_pedido_abierto(client, csrf, producto_id, referencia_entrega='Carlos retiro')
    cola_resp = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/cobro-avanzado',
        json={'enviar_cocina': True},
        headers={'X-CSRFToken': csrf},
    )
    assert cola_resp.status_code == 200
    cola_data = cola_resp.get_json()
    assert cola_data['checkout_url'].endswith(f'/ventas/pos?cola_id={cola_data["cola_id"]}')

    checkout_resp = client.get(cola_data['checkout_url'])
    assert checkout_resp.status_code == 200
    checkout_html = checkout_resp.get_data(as_text=True)
    assert f'#{pedido_id:03d}' in checkout_html
    assert 'Carlos retiro' in checkout_html

    with app.app_context():
        metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        assert metodo is not None
        cola = ColaCobro.query.get(cola_data['cola_id'])
        assert cola.estado == 'en_proceso'

    venta_resp = client.post(
        '/ventas/procesar',
        json={
            'cola_cobro_id': cola_data['cola_id'],
            'pagos': [{'id_metodo_pago': metodo.id_metodo_pago, 'monto': 30000}],
            'id_cliente': 1,
            'client_request_id': f'gastronomia-{pedido_id}',
        },
        headers={'X-CSRFToken': csrf},
    )
    assert venta_resp.status_code == 200
    venta_json = venta_resp.get_json()
    assert venta_json['success'] is True

    ticket_resp = client.get(f'/ventas/{venta_json["id_venta"]}/ticket?preview=1')
    assert ticket_resp.status_code == 200
    ticket_html = ticket_resp.get_data(as_text=True)
    assert f'#{pedido_id:03d}' in ticket_html
    assert 'Carlos retiro' in ticket_html

    with app.app_context():
        pedido = GastronomiaPedido.query.get(pedido_id)
        assert pedido.estado == 'enviado_cocina'
        assert pedido.pago is not None
        assert pedido.pago.id_venta == venta_json['id_venta']
        assert pedido.pago.metodo_pago == 'efectivo'
        assert float(pedido.pago.total_cobrado) == 30000
        cola = ColaCobro.query.get(cola_data['cola_id'])
        assert cola.estado == 'cobrado'
        assert cola.tipo_origen == 'gastronomia'
        assert cola.get_metadata()['gastronomia_pago_registrado'] is True
        assert Venta.query.get(venta_json['id_venta']) is not None
        assert GastronomiaPedidoPago.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).count() == 1
