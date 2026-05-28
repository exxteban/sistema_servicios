import re

from app import create_app, db
from app.models import Cliente, Usuario
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaGrupoOpciones,
    GastronomiaMesa,
    GastronomiaOpcionProducto,
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


def _crear_menu_para_pedidos(app, nombre_cliente='Resto Uno', username='resto_uno'):
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
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Hamburguesas')
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
            nombre='Clasica',
            precio=15000,
        )
        db.session.add(producto)
        db.session.flush()
        grupo = GastronomiaGrupoOpciones(
            cliente_id=cliente.id_cliente,
            producto_id=producto.id_producto,
            nombre='Extras',
            tipo='extra',
            max_selecciones=2,
        )
        db.session.add(grupo)
        db.session.flush()
        opcion = GastronomiaOpcionProducto(
            cliente_id=cliente.id_cliente,
            grupo_id=grupo.id_grupo,
            nombre='Queso',
            precio_delta=2500,
        )
        db.session.add(opcion)
        db.session.commit()
        return cliente.id_cliente, producto.id_producto, opcion.id_opcion


def _agregar_producto(app, cliente_id: int, categoria_nombre: str, nombre: str, precio: int) -> int:
    with app.app_context():
        categoria = GastronomiaCategoria.query.filter_by(cliente_id=cliente_id, nombre=categoria_nombre).first()
        assert categoria is not None
        producto = GastronomiaProducto(
            cliente_id=cliente_id,
            categoria_id=categoria.id_categoria,
            nombre=nombre,
            precio=precio,
        )
        db.session.add(producto)
        db.session.commit()
        return producto.id_producto


def _agregar_mesa(app, cliente_id: int, nombre: str) -> None:
    with app.app_context():
        db.session.add(GastronomiaMesa(cliente_id=cliente_id, nombre=nombre))
        db.session.commit()


def test_pos_page_carga_y_pedido_se_guarda_con_totales_backend():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id, opcion_id = _crear_menu_para_pedidos(app)
    _agregar_mesa(app, cliente_id, 'A1')
    _loguear(client, app, 'resto_uno')

    page = client.get('/gastronomia/pos')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'POS Touch' in html
    csrf = _csrf(html)

    response = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mesa',
            'mesa': 'A1',
            'referencia_entrega': 'Juan Perez',
            'items': [
                {
                    'producto_id': producto_id,
                    'cantidad': 2,
                    'opciones': [opcion_id],
                    'notas': 'Sin cebolla',
                }
            ],
        },
        headers={'X-CSRFToken': csrf},
    )

    assert response.status_code == 201
    pedido = response.get_json()['pedido']
    assert pedido['estado'] == 'abierto'
    assert pedido['tipo_pedido'] == 'mesa'
    assert pedido['mesa'] == 'A1'
    assert pedido['referencia_entrega'] == 'Juan Perez'
    assert pedido['codigo_entrega'] == f"#{pedido['id_pedido']:03d}"
    assert pedido['total'] == 35000
    assert pedido['items'][0]['precio_unitario'] == 17500
    assert pedido['items'][0]['modificadores'][0]['nombre_opcion'] == 'Queso'
    with app.app_context():
        assert GastronomiaPedido.query.filter_by(cliente_id=cliente_id).count() == 1


def test_pedido_se_envia_a_cocina_y_no_se_filtra_entre_clientes():
    app = create_app('testing')
    client_uno = app.test_client()
    client_dos = app.test_client()
    _cliente_uno_id, producto_uno_id, _opcion_uno_id = _crear_menu_para_pedidos(app, 'Resto Uno', 'resto_uno')
    _cliente_dos_id, producto_dos_id, _opcion_dos_id = _crear_menu_para_pedidos(app, 'Resto Dos', 'resto_dos')

    _loguear(client_uno, app, 'resto_uno')
    csrf_uno = _csrf(client_uno.get('/gastronomia/pos').get_data(as_text=True))
    pedido_resp = client_uno.post(
        '/api/gastronomia/pedidos',
        json={'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_uno_id, 'cantidad': 1}]},
        headers={'X-CSRFToken': csrf_uno},
    )
    assert pedido_resp.status_code == 201
    pedido_id = pedido_resp.get_json()['pedido']['id_pedido']

    enviado_resp = client_uno.post(
        f'/api/gastronomia/pedidos/{pedido_id}/enviar-cocina',
        json={},
        headers={'X-CSRFToken': csrf_uno},
    )
    assert enviado_resp.status_code == 200
    assert enviado_resp.get_json()['pedido']['estado'] == 'enviado_cocina'

    _loguear(client_dos, app, 'resto_dos')
    csrf_dos = _csrf(client_dos.get('/gastronomia/pos').get_data(as_text=True))
    ajeno_resp = client_dos.get(f'/api/gastronomia/pedidos/{pedido_id}')
    assert ajeno_resp.status_code == 404
    propio_resp = client_dos.post(
        '/api/gastronomia/pedidos',
        json={'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_dos_id, 'cantidad': 1}]},
        headers={'X-CSRFToken': csrf_dos},
    )
    assert propio_resp.status_code == 201
    listado = client_dos.get('/api/gastronomia/pedidos')
    assert len(listado.get_json()['pedidos']) == 1


def test_pedido_abierto_se_puede_editar_y_recalcula_total():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id, opcion_id = _crear_menu_para_pedidos(app, 'Resto Edicion', 'resto_edicion')
    producto_secundario_id = _agregar_producto(app, cliente_id, 'Hamburguesas', 'Doble', 22000)
    _agregar_mesa(app, cliente_id, 'M1')
    _loguear(client, app, 'resto_edicion')

    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))
    crear_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mesa',
            'mesa': 'M1',
            'referencia_entrega': 'Juan',
            'notas': 'Primera version',
            'items': [
                {
                    'producto_id': producto_id,
                    'cantidad': 2,
                    'opciones': [opcion_id],
                    'notas': 'Sin cebolla',
                }
            ],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert crear_resp.status_code == 201
    pedido_id = crear_resp.get_json()['pedido']['id_pedido']

    editar_resp = client.put(
        f'/api/gastronomia/pedidos/{pedido_id}',
        json={
            'tipo_pedido': 'retiro',
            'mesa': '',
            'referencia_entrega': 'Maria retiro',
            'notas': 'Cambiar a retiro',
            'items': [
                {
                    'producto_id': producto_secundario_id,
                    'cantidad': 3,
                    'opciones': [],
                    'notas': 'Bien cocido',
                }
            ],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert editar_resp.status_code == 200
    pedido = editar_resp.get_json()['pedido']
    assert pedido['id_pedido'] == pedido_id
    assert pedido['estado'] == 'abierto'
    assert pedido['tipo_pedido'] == 'retiro'
    assert pedido['mesa'] is None
    assert pedido['referencia_entrega'] == 'Maria retiro'
    assert pedido['notas'] == 'Cambiar a retiro'
    assert pedido['total'] == 66000
    assert len(pedido['items']) == 1
    assert pedido['items'][0]['producto_id'] == producto_secundario_id
    assert pedido['items'][0]['cantidad'] == 3
    assert pedido['items'][0]['precio_unitario'] == 22000
    assert pedido['items'][0]['modificadores'] == []

    with app.app_context():
        pedido_db = GastronomiaPedido.query.filter_by(cliente_id=cliente_id, id_pedido=pedido_id).first()
        assert pedido_db is not None
        assert pedido_db.tipo_pedido == 'retiro'
        assert pedido_db.mesa is None
        assert float(pedido_db.total) == 66000
        assert pedido_db.items.count() == 1
        evento = GastronomiaPedidoEvento.query.filter_by(
            cliente_id=cliente_id,
            pedido_id=pedido_id,
            tipo='pedido_actualizado',
        ).first()
        assert evento is not None


def test_stock_controlado_descuenta_agota_y_se_restaura_al_cancelar():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id, _opcion_id = _crear_menu_para_pedidos(app, 'Resto Stock', 'resto_stock')
    with app.app_context():
        producto = GastronomiaProducto.query.filter_by(cliente_id=cliente_id, id_producto=producto_id).one()
        producto.control_stock_venta = True
        producto.stock_disponible = 3
        db.session.commit()
    _loguear(client, app, 'resto_stock')

    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))
    crear_resp = client.post(
        '/api/gastronomia/pedidos',
        json={'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_id, 'cantidad': 2}]},
        headers={'X-CSRFToken': csrf},
    )
    assert crear_resp.status_code == 201
    pedido_id = crear_resp.get_json()['pedido']['id_pedido']

    with app.app_context():
        producto = GastronomiaProducto.query.filter_by(cliente_id=cliente_id, id_producto=producto_id).one()
        assert producto.stock_disponible == 1
        assert producto.disponible is True

    editar_resp = client.put(
        f'/api/gastronomia/pedidos/{pedido_id}',
        json={'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_id, 'cantidad': 3}]},
        headers={'X-CSRFToken': csrf},
    )
    assert editar_resp.status_code == 200
    with app.app_context():
        producto = GastronomiaProducto.query.filter_by(cliente_id=cliente_id, id_producto=producto_id).one()
        assert producto.stock_disponible == 0
        assert producto.disponible is False

    sin_agotados = client.get('/api/gastronomia/productos?publico=1')
    assert sin_agotados.status_code == 200
    assert sin_agotados.get_json()['productos'] == []

    con_agotados = client.get('/api/gastronomia/productos?publico=1&agotados=1')
    assert con_agotados.status_code == 200
    producto_publico = con_agotados.get_json()['productos'][0]
    assert producto_publico['disponible'] is False
    assert producto_publico['stock_disponible'] == 0

    cancelar_resp = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/estado',
        json={'estado': 'cancelado'},
        headers={'X-CSRFToken': csrf},
    )
    assert cancelar_resp.status_code == 200
    with app.app_context():
        producto = GastronomiaProducto.query.filter_by(cliente_id=cliente_id, id_producto=producto_id).one()
        assert producto.stock_disponible == 3
        assert producto.disponible is True


def test_stock_controlado_rechaza_sobreventa_y_conserva_stock():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id, _opcion_id = _crear_menu_para_pedidos(app, 'Resto Sin Sobreventa', 'resto_sin_sobreventa')
    with app.app_context():
        producto = GastronomiaProducto.query.filter_by(cliente_id=cliente_id, id_producto=producto_id).one()
        producto.control_stock_venta = True
        producto.stock_disponible = 1
        db.session.commit()
    _loguear(client, app, 'resto_sin_sobreventa')

    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))
    crear_resp = client.post(
        '/api/gastronomia/pedidos',
        json={'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_id, 'cantidad': 2}]},
        headers={'X-CSRFToken': csrf},
    )
    assert crear_resp.status_code == 400
    assert 'No hay stock suficiente' in crear_resp.get_json()['mensaje']

    with app.app_context():
        producto = GastronomiaProducto.query.filter_by(cliente_id=cliente_id, id_producto=producto_id).one()
        assert producto.stock_disponible == 1
        assert producto.disponible is True


def test_pedido_no_se_puede_editar_despues_de_enviarse_a_cocina():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id, _opcion_id = _crear_menu_para_pedidos(app, 'Resto Bloqueado', 'resto_bloqueado')
    _loguear(client, app, 'resto_bloqueado')

    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))
    crear_resp = client.post(
        '/api/gastronomia/pedidos',
        json={'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_id, 'cantidad': 1}]},
        headers={'X-CSRFToken': csrf},
    )
    assert crear_resp.status_code == 201
    pedido_id = crear_resp.get_json()['pedido']['id_pedido']

    enviar_resp = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/enviar-cocina',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert enviar_resp.status_code == 200

    editar_resp = client.put(
        f'/api/gastronomia/pedidos/{pedido_id}',
        json={'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_id, 'cantidad': 2}]},
        headers={'X-CSRFToken': csrf},
    )
    assert editar_resp.status_code == 400
    assert editar_resp.get_json()['mensaje'] == 'Solo se pueden editar pedidos abiertos.'
