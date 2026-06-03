import re

from app import create_app, db
from app.models import Caja, Cliente, ColaCobro, DetalleVenta, MetodoPago, MovimientoCaja, PagoVenta, SesionCaja, Usuario, Venta
from app.models.inventario import MovimientoStock
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


def test_caja_actual_permite_anular_venta_desde_modal_de_movimiento():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Caja Actual Anula', 'resto_caja_actual_anula')
    _loguear(client, app, 'resto_caja_actual_anula')
    _abrir_caja(app, 'resto_caja_actual_anula')

    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)
    cobrar_resp = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200

    with app.app_context():
        pago = GastronomiaPedidoPago.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).one()
        venta_id = pago.id_venta

    caja_actual = client.get('/caja/')
    assert caja_actual.status_code == 200
    html = caja_actual.get_data(as_text=True)
    assert 'Ventas cobradas para anular' not in client.get('/gastronomia/caja').get_data(as_text=True)
    assert f'data-venta-id="{venta_id}"' in html
    assert 'data-venta-anulable="1"' in html
    assert 'Anular venta' in html

    resumen = client.get('/caja/api/estado/resumen')
    assert resumen.status_code == 200
    movimiento = next(item for item in resumen.get_json()['movimientos'] if item.get('venta_id') == venta_id)
    assert movimiento['venta_anulable'] is True


def test_cobro_directo_cierra_cola_gastronomia_activa():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Cola Directa', 'resto_cola_directa')
    _loguear(client, app, 'resto_cola_directa')
    _abrir_caja(app, 'resto_cola_directa')

    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)

    with app.app_context():
        from gastronomia.services.venta_integration_service import crear_cola_cobro_central_desde_pedido

        usuario = Usuario.query.filter_by(username='resto_cola_directa').first()
        pedido = GastronomiaPedido.query.get(pedido_id)
        cola = crear_cola_cobro_central_desde_pedido(
            pedido,
            usuario.id_usuario,
            enviar_cocina=False,
        )
        cola.estado = 'en_proceso'
        cola.id_usuario_destino = usuario.id_usuario
        db.session.commit()
        cola_id = cola.id

    cobrar_resp = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200

    with app.app_context():
        cola = ColaCobro.query.get(cola_id)
        assert cola.estado == 'cobrado'
        assert cola.id_usuario_destino is not None
        assert cola.fecha_cobro is not None
        metadata = cola.get_metadata()
        assert metadata['gastronomia_pago_registrado'] is True
        assert metadata['gastronomia_cobro_directo_caja'] is True
        assert metadata['venta_id']
        pago = GastronomiaPedidoPago.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).first()
        assert pago is not None
        assert metadata['venta_id'] == pago.id_venta


def test_cierre_caja_regulariza_cola_gastronomia_ya_cobrada():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id = _crear_producto(app, 'Resto Cierre Cola', 'resto_cierre_cola')
    _loguear(client, app, 'resto_cierre_cola')
    _abrir_caja(app, 'resto_cierre_cola')

    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)

    with app.app_context():
        from gastronomia.services.venta_integration_service import crear_cola_cobro_central_desde_pedido

        usuario = Usuario.query.filter_by(username='resto_cierre_cola').first()
        pedido = GastronomiaPedido.query.get(pedido_id)
        cola = crear_cola_cobro_central_desde_pedido(pedido, usuario.id_usuario, enviar_cocina=False)
        cola.estado = 'en_proceso'
        cola.id_usuario_destino = usuario.id_usuario
        db.session.commit()
        cola_id = cola.id

    cobrar_resp = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200

    with app.app_context():
        usuario = Usuario.query.filter_by(username='resto_cierre_cola').first()
        cola = ColaCobro.query.get(cola_id)
        cola.estado = 'en_proceso'
        cola.id_usuario_destino = usuario.id_usuario
        cola.fecha_cobro = None
        db.session.commit()

    cierre_resp = client.get('/caja/cerrar')
    assert cierre_resp.status_code == 200
    assert 'No puede cerrar la caja mientras tenga pendientes' not in cierre_resp.get_data(as_text=True)

    with app.app_context():
        cola = ColaCobro.query.get(cola_id)
        assert cola.estado == 'cobrado'
        assert cola.fecha_cobro is not None
        assert cola.get_metadata()['regularizado_en_cierre_caja'] is True


def test_delivery_guarda_contacto_ticket_y_seguimiento_publico():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id = _crear_producto(app, 'Resto Delivery', 'resto_delivery')
    _loguear(client, app, 'resto_delivery')
    delivery_page = client.get('/gastronomia/delivery')
    assert delivery_page.status_code == 200
    assert 'Nuevo delivery' in delivery_page.get_data(as_text=True)
    pos_html = client.get('/gastronomia/pos?tipo=delivery').get_data(as_text=True)
    csrf = _csrf(pos_html)
    assert 'delivery-shipping-cost' in pos_html
    assert 'delivery-location-url' in pos_html
    assert 'delivery-open-location-map' in pos_html

    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'delivery',
            'referencia_entrega': 'Carla',
            'celular_cliente': '0981123456',
            'direccion_entrega': 'Av. Siempre Viva 742',
            'ubicacion_entrega_url': 'https://www.google.com/maps/place/test/@-25.3001,-57.6359,17z',
            'tiempo_estimado_minutos': 35,
            'costo_envio': 7000,
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido_resp.status_code == 201
    pedido = pedido_resp.get_json()['pedido']
    assert pedido['tipo_pedido'] == 'delivery'
    assert pedido['celular_cliente'] == '0981123456'
    assert pedido['direccion_entrega'] == 'Av. Siempre Viva 742'
    assert pedido['ubicacion_entrega_url'].startswith('https://www.google.com/maps')
    assert pedido['destino_latitud'] == -25.3001
    assert pedido['destino_longitud'] == -57.6359
    assert pedido['tiempo_estimado_minutos'] == 35
    assert pedido['costo_envio'] == 7000
    assert pedido['subtotal'] == 30000
    assert pedido['total'] == 37000
    assert pedido['codigo_publico']
    filtrado_resp = client.get('/api/gastronomia/pedidos?tipo_pedido=delivery')
    assert filtrado_resp.status_code == 200
    assert [item['id_pedido'] for item in filtrado_resp.get_json()['pedidos']] == [pedido['id_pedido']]

    cocina_resp = client.post(
        f'/api/gastronomia/pedidos/{pedido["id_pedido"]}/enviar-cocina',
        headers={'X-CSRFToken': csrf},
    )
    assert cocina_resp.status_code == 200
    assert client.post(
        f'/api/gastronomia/pedidos/{pedido["id_pedido"]}/estado',
        json={'estado': 'listo'},
        headers={'X-CSRFToken': csrf},
    ).status_code == 200
    en_camino_resp = client.post(
        f'/api/gastronomia/pedidos/{pedido["id_pedido"]}/estado',
        json={'estado': 'en_camino'},
        headers={'X-CSRFToken': csrf},
    )
    assert en_camino_resp.status_code == 200
    assert en_camino_resp.get_json()['pedido']['estado'] == 'en_camino'

    ticket_html = client.get(f'/gastronomia/pedidos/{pedido["id_pedido"]}/ticket?preview=1').get_data(as_text=True)
    assert 'DELIVERY' in ticket_html
    assert '0981123456' in ticket_html
    assert 'Av. Siempre Viva 742' in ticket_html
    assert 'Envio' in ticket_html
    seguimiento_resp = client.get(f'/gastronomia/pedido/{pedido["codigo_publico"]}')
    assert seguimiento_resp.headers['Cache-Control'] == 'no-store, no-cache, must-revalidate, max-age=0'
    seguimiento_html = seguimiento_resp.get_data(as_text=True)
    assert 'Tu pedido ya salio con el delivery.' in seguimiento_html
    assert '35 minutos' in seguimiento_html
    seguimiento_estado_resp = client.get(f'/gastronomia/pedido/{pedido["codigo_publico"]}/estado')
    assert seguimiento_estado_resp.status_code == 200
    assert seguimiento_estado_resp.headers['Cache-Control'] == 'no-store, no-cache, must-revalidate, max-age=0'
    seguimiento_estado = seguimiento_estado_resp.get_json()
    assert seguimiento_estado['pedido']['estado'] == 'en_camino'
    assert seguimiento_estado['pedido']['mensaje'] == 'Tu pedido ya salio con el delivery.'


def test_caja_actualiza_costo_envio_delivery_antes_de_cobrar():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Caja Delivery', 'resto_caja_delivery')
    _loguear(client, app, 'resto_caja_delivery')
    _abrir_caja(app, 'resto_caja_delivery')
    page = client.get('/gastronomia/caja')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'shipping-cost' in html
    csrf = _csrf(html)

    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'delivery',
            'referencia_entrega': 'Rosa',
            'celular_cliente': '0981555444',
            'direccion_entrega': 'Centro 123',
            'costo_envio': 5000,
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido_resp.status_code == 201
    pedido_id = pedido_resp.get_json()['pedido']['id_pedido']

    cobrar_resp = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo', 'costo_envio': 8000},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200
    pedido = cobrar_resp.get_json()['pedido']
    assert pedido['subtotal'] == 30000
    assert pedido['costo_envio'] == 8000
    assert pedido['total'] == 38000
    assert pedido['pago']['subtotal'] == 38000
    assert pedido['pago']['total_cobrado'] == 38000

    ticket_html = client.get(f'/gastronomia/pedidos/{pedido_id}/ticket?preview=1').get_data(as_text=True)
    assert 'Envio' in ticket_html
    assert '38.000' in ticket_html

    with app.app_context():
        pedido_db = GastronomiaPedido.query.filter_by(cliente_id=cliente_id, id_pedido=pedido_id).first()
        assert pedido_db is not None
        assert float(pedido_db.costo_envio) == 8000
        pago = pedido_db.pago
        assert float(pago.total_cobrado) == 38000
        venta = Venta.query.get(pago.id_venta)
        assert venta is not None
        assert float(venta.subtotal) == 38000
        assert float(venta.total) == 38000
        assert DetalleVenta.query.filter_by(id_venta=venta.id_venta).count() == 2


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
        json={'metodo_pago': 'tarjeta', 'referencia': 'POS-001'},
        headers={'X-CSRFToken': csrf_dos},
    )
    assert cobrar_resp.status_code == 200

    duplicado_resp = client_dos.post(
        f'/api/gastronomia/caja/pedidos/{pedido_dos_id}/cobrar',
        json={'metodo_pago': 'tarjeta', 'referencia': 'POS-001'},
        headers={'X-CSRFToken': csrf_dos},
    )
    assert duplicado_resp.status_code == 400
    with app.app_context():
        pedido = GastronomiaPedido.query.get(pedido_dos_id)
        assert pedido.estado == 'listo'


def test_caja_reserva_pago_antes_de_crear_venta_central(monkeypatch):
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Cobro Atomico', 'resto_cobro_atomico')
    _loguear(client, app, 'resto_cobro_atomico')
    _abrir_caja(app, 'resto_cobro_atomico')

    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)

    from gastronomia.services import caja_service

    original = caja_service.crear_venta_central_desde_pedido
    reserva_observada = {'ok': False}

    def _crear_venta_verificando_reserva(pedido, usuario_id, data, *, descuento):
        pago_reservado = GastronomiaPedidoPago.query.filter_by(
            cliente_id=cliente_id,
            pedido_id=pedido_id,
        ).one()
        assert pago_reservado.id_venta is None
        reserva_observada['ok'] = True
        return original(pedido, usuario_id, data, descuento=descuento)

    monkeypatch.setattr(caja_service, 'crear_venta_central_desde_pedido', _crear_venta_verificando_reserva)

    cobrar_resp = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200
    assert reserva_observada['ok'] is True

    with app.app_context():
        pagos = GastronomiaPedidoPago.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).all()
        assert len(pagos) == 1
        assert pagos[0].id_venta is not None
        assert Venta.query.count() == 1


def test_caja_exige_referencia_si_metodo_pago_la_requiere():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id = _crear_producto(app, 'Resto Referencia', 'resto_referencia')
    _loguear(client, app, 'resto_referencia')
    _abrir_caja(app, 'resto_referencia')

    with app.app_context():
        metodo = MetodoPago(nombre='QR Referenciado', requiere_referencia=True, activo=True)
        db.session.add(metodo)
        db.session.commit()
        metodo_id = metodo.id_metodo_pago

    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)
    sin_referencia = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'id_metodo_pago': metodo_id},
        headers={'X-CSRFToken': csrf},
    )
    assert sin_referencia.status_code == 400
    assert 'requiere referencia' in sin_referencia.get_json()['mensaje']

    con_referencia = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'id_metodo_pago': metodo_id, 'referencia': 'QR-123'},
        headers={'X-CSRFToken': csrf},
    )
    assert con_referencia.status_code == 200


def test_anular_venta_central_cancela_pedido_gastronomico_y_restaura_stock():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Anulacion', 'resto_anulacion')
    _loguear(client, app, 'resto_anulacion')
    _abrir_caja(app, 'resto_anulacion')

    with app.app_context():
        producto = GastronomiaProducto.query.get(producto_id)
        producto.control_stock_venta = True
        producto.stock_disponible = 2
        db.session.commit()

    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)
    cobrar_resp = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200

    with app.app_context():
        from gastronomia.services.venta_integration_service import registrar_anulacion_gastronomia_desde_venta_central

        pago = GastronomiaPedidoPago.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).one()
        venta = Venta.query.get(pago.id_venta)
        eventos = registrar_anulacion_gastronomia_desde_venta_central(venta, pago.usuario_id)
        venta.estado = 'anulada'
        db.session.commit()

        pedido = GastronomiaPedido.query.get(pedido_id)
        producto = GastronomiaProducto.query.get(producto_id)
        assert [evento['tipo'] for evento in eventos] == ['pedido_cancelado', 'pedido_cobro_anulado']
        assert pedido.estado == 'cancelado'
        assert pedido.pago is None
        assert GastronomiaPedidoPago.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).count() == 0
        assert producto.stock_disponible == 2
        assert Venta.query.get(venta.id_venta).estado == 'anulada'


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


def test_caja_avisa_si_no_hay_sesion_abierta_y_dashboard_resalta_pendientes():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id = _crear_producto(app, 'Resto Alerta Caja', 'resto_alerta_caja')
    _loguear(client, app, 'resto_alerta_caja')

    caja_html = client.get('/gastronomia/caja').get_data(as_text=True)
    assert 'data-sesion-caja-abierta="0"' in caja_html
    assert 'Abri una caja central antes de cobrar pedidos desde esta pantalla.' in caja_html

    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))
    _crear_pedido_listo(client, csrf, producto_id)

    dashboard_html = client.get('/gastronomia/').get_data(as_text=True)
    assert 'gastro-dashboard-card--alert' in dashboard_html
    assert '1 pendiente' in dashboard_html
    assert 'Hay pedidos sin cobrar esperando en caja.' in dashboard_html


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


def test_pedido_cobrado_no_se_cancela_por_via_operativa_y_conserva_caja_y_stock():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Cobro Bloqueo', 'resto_cobro_bloqueo')
    _loguear(client, app, 'resto_cobro_bloqueo')
    _abrir_caja(app, 'resto_cobro_bloqueo')

    with app.app_context():
        producto = GastronomiaProducto.query.get(producto_id)
        producto.control_stock_venta = True
        producto.stock_disponible = 5
        db.session.commit()

    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)
    cobrar_resp = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200

    cancelar_resp = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/estado',
        json={'estado': 'cancelado'},
        headers={'X-CSRFToken': csrf},
    )
    assert cancelar_resp.status_code == 400
    assert 'cobrado' in cancelar_resp.get_json()['mensaje'].lower()

    with app.app_context():
        pedido = GastronomiaPedido.query.get(pedido_id)
        producto = GastronomiaProducto.query.get(producto_id)
        # El pedido sigue cobrado: ni el stock ni la caja se descuadran.
        assert pedido.estado != 'cancelado'
        assert pedido.pago is not None
        assert producto.stock_disponible == 4
        assert Venta.query.get(pedido.pago.id_venta).estado != 'anulada'
        assert MovimientoStock.query.filter_by(
            id_producto=producto_id,
            referencia_tipo='gastronomia_restaura',
        ).count() == 0
