from app import create_app, db
from app.models import ColaCobro, MetodoPago, Usuario, Venta
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoPago
from gastronomia.services.venta_integration_service import registrar_anulacion_gastronomia_desde_venta_central
from test_gastronomia_caja import _abrir_caja, _crear_pedido_abierto, _crear_producto, _csrf, _loguear


def _crear_venta_gastronomia_desde_checkout(client, app, username, producto_id):
    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))
    pedido_id = _crear_pedido_abierto(client, csrf, producto_id, referencia_entrega='Regularizacion')
    cola_resp = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/cobro-avanzado',
        json={'enviar_cocina': True},
        headers={'X-CSRFToken': csrf},
    )
    assert cola_resp.status_code == 200
    cola_id = cola_resp.get_json()['cola_id']
    client.get(cola_resp.get_json()['checkout_url'])

    with app.app_context():
        metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
        assert metodo is not None
        metodo_id = metodo.id_metodo_pago

    venta_resp = client.post(
        '/ventas/procesar',
        json={
            'cola_cobro_id': cola_id,
            'pagos': [{'id_metodo_pago': metodo_id, 'monto': 30000}],
            'id_cliente': 1,
            'client_request_id': f'gastronomia-regularizacion-{pedido_id}',
        },
        headers={'X-CSRFToken': csrf},
    )
    assert venta_resp.status_code == 200
    return pedido_id, cola_id, venta_resp.get_json()['id_venta']


def _simular_cola_historica_en_proceso(app, username, pedido_id, cola_id):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        cola = ColaCobro.query.get(cola_id)
        pago = GastronomiaPedidoPago.query.filter_by(pedido_id=pedido_id).first()
        if pago:
            db.session.delete(pago)
        cola.estado = 'en_proceso'
        cola.id_usuario_destino = usuario.id_usuario
        cola.fecha_cobro = None
        db.session.commit()


def test_cierre_regulariza_cola_gastronomia_con_venta_central_sin_pago():
    app = create_app('testing')
    client = app.test_client()
    username = 'resto_regulariza_venta'
    _cliente_id, producto_id = _crear_producto(app, 'Resto Regulariza Venta', username)
    _loguear(client, app, username)
    _abrir_caja(app, username)

    pedido_id, cola_id, venta_id = _crear_venta_gastronomia_desde_checkout(client, app, username, producto_id)
    _simular_cola_historica_en_proceso(app, username, pedido_id, cola_id)

    cierre_resp = client.get('/caja/cerrar')
    assert cierre_resp.status_code == 200
    assert 'No puede cerrar la caja mientras tenga pendientes' not in cierre_resp.get_data(as_text=True)

    with app.app_context():
        cola = ColaCobro.query.get(cola_id)
        assert cola.estado == 'cobrado'
        assert cola.get_metadata()['venta_id'] == venta_id
        assert cola.get_metadata()['regularizado_en_cierre_caja'] is True


def test_anular_venta_gastronomia_cancela_cola_activa_sin_pago():
    app = create_app('testing')
    client = app.test_client()
    username = 'resto_anula_cola'
    _cliente_id, producto_id = _crear_producto(app, 'Resto Anula Cola', username)
    _loguear(client, app, username)
    _abrir_caja(app, username)

    pedido_id, cola_id, venta_id = _crear_venta_gastronomia_desde_checkout(client, app, username, producto_id)
    _simular_cola_historica_en_proceso(app, username, pedido_id, cola_id)

    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        venta = Venta.query.get(venta_id)
        eventos = registrar_anulacion_gastronomia_desde_venta_central(venta, usuario.id_usuario)
        venta.estado = 'anulada'
        db.session.commit()

        cola = ColaCobro.query.get(cola_id)
        pedido = GastronomiaPedido.query.get(pedido_id)
        assert cola.estado == 'cancelado'
        assert cola.get_metadata()['gastronomia_venta_anulada'] is True
        assert pedido.estado == 'cancelado'
        assert GastronomiaPedidoPago.query.filter_by(pedido_id=pedido_id).count() == 0
        assert 'pedido_cancelado' in [evento['tipo'] for evento in eventos]


def test_cierre_cancela_cola_gastronomia_si_pago_apunta_a_venta_anulada():
    app = create_app('testing')
    client = app.test_client()
    username = 'resto_regulariza_anulada'
    _cliente_id, producto_id = _crear_producto(app, 'Resto Regulariza Anulada', username)
    _loguear(client, app, username)
    _abrir_caja(app, username)

    pedido_id, cola_id, venta_id = _crear_venta_gastronomia_desde_checkout(client, app, username, producto_id)

    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        cola = ColaCobro.query.get(cola_id)
        venta = Venta.query.get(venta_id)
        venta.estado = 'anulada'
        cola.estado = 'en_proceso'
        cola.id_usuario_destino = usuario.id_usuario
        cola.fecha_cobro = None
        db.session.commit()

    cierre_resp = client.get('/caja/cerrar')
    assert cierre_resp.status_code == 200
    assert 'No puede cerrar la caja mientras tenga pendientes' not in cierre_resp.get_data(as_text=True)

    with app.app_context():
        cola = ColaCobro.query.get(cola_id)
        assert cola.estado == 'cancelado'
        assert cola.get_metadata()['venta_id'] == venta_id
        assert cola.get_metadata()['regularizacion_motivo'] == 'venta_gastronomia_anulada'
        assert GastronomiaPedidoPago.query.filter_by(pedido_id=pedido_id).count() == 1
