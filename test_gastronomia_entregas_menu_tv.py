import re
from datetime import datetime, timedelta

from app import create_app, db
from app.models import Cliente, TiendaPromocion, TiendaPromocionGastronomiaProducto, Usuario
from app.utils.helpers import today_local, utc_bounds_for_local_dates
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaPedido,
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
            imagen_url='https://cdn.example.com/milanesa.jpg',
            orden=1,
        )
        oculto = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Secreto',
            precio=1,
            visible=False,
        )
        solo_menu = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Solo menu',
            precio=9000,
            visible=True,
            visible_en_tv=False,
        )
        agotado = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Empanada',
            precio=6000,
            disponible=False,
            orden=2,
        )
        db.session.add_all([producto, oculto, solo_menu, agotado])
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


def test_entregas_incluye_cobrados_sin_fecha_entrega_por_fecha_pago():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id, _agotado_id = _crear_base(app, 'Resto Cobrado Entregas', 'entregas_cobrado', 'entregas-cobrado')

    _loguear(client, app, 'entregas_cobrado')
    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))
    pedido_id = _crear_pedido(client, csrf, producto_id, 'Pago Caja')

    with app.app_context():
        usuario = Usuario.query.filter_by(username='entregas_cobrado').first()
        inicio_hoy, _fin_hoy = utc_bounds_for_local_dates(today_local(), today_local())
        pedido = GastronomiaPedido.query.get(pedido_id)
        pedido.estado = 'cobrado'
        pedido.fecha_entrega = None
        db.session.add(GastronomiaPedidoPago(
            cliente_id=pedido.cliente_id,
            pedido_id=pedido.id_pedido,
            usuario_id=usuario.id_usuario,
            metodo_pago='efectivo',
            subtotal=pedido.total,
            total_cobrado=pedido.total,
            fecha_pago=inicio_hoy + timedelta(hours=3),
        ))
        db.session.commit()

    response = client.get('/api/gastronomia/entregas?estado=cobrado')
    assert response.status_code == 200
    data = response.get_json()
    assert data['fecha'] == today_local().isoformat()
    assert [pedido['id_pedido'] for pedido in data['pedidos']] == [pedido_id]


def test_entregas_api_pagina_resultados_filtrados_y_resumen_total():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id, _agotado_id = _crear_base(app, 'Resto Entregas Paginadas', 'entregas_paginadas', 'entregas-paginadas')

    _loguear(client, app, 'entregas_paginadas')
    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))
    pedidos = []
    for index in range(5):
        pedido_id = _crear_pedido(client, csrf, producto_id, f'Pedido {index}')
        _entregar(client, csrf, pedido_id)
        pedidos.append(pedido_id)

    response = client.get('/api/gastronomia/entregas?fecha=hoy&page=2&per_page=2')
    assert response.status_code == 200
    data = response.get_json()
    assert data['paginacion'] == {
        'pagina': 2,
        'por_pagina': 2,
        'total': 5,
        'paginas': 3,
        'tiene_anterior': True,
        'tiene_siguiente': True,
    }
    assert [pedido['id_pedido'] for pedido in data['pedidos']] == [pedidos[2], pedidos[1]]
    assert data['resumen']['cantidad_entregada'] == 5


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
    assert productos[0]['imagen_url'] == 'https://cdn.example.com/milanesa.jpg'
    assert 'Secreto' not in nombres
    assert 'Solo menu' not in nombres

    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).first()
        config.menu_tv_mostrar_agotados = True
        db.session.commit()
    con_agotados = client.get('/api/gastronomia/public/menu-tv/resto-tv')
    productos = con_agotados.get_json()['categorias'][0]['productos']
    nombres = [producto['nombre'] for producto in productos]
    assert nombres == ['Milanesa', 'Empanada']
    assert productos[1]['disponible'] is False

    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).first()
        config.menu_tv_publico_activo = False
        db.session.commit()
    assert client.get('/api/gastronomia/public/menu-tv/resto-tv').status_code == 404
    assert client.get('/gastronomia/menu-tv/resto-tv').status_code == 404


def test_menu_tv_publico_muestra_promocion_gastronomica_activa():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id, _agotado_id = _crear_base(app, 'Resto TV Promo', 'resto_tv_promo', 'resto-tv-promo')
    with app.app_context():
        promocion = TiendaPromocion(
            id_cliente=cliente_id,
            nombre='Promo TV',
            tipo='porcentaje',
            valor=20,
            fecha_inicio=datetime.utcnow() - timedelta(hours=1),
            fecha_fin=datetime.utcnow() + timedelta(hours=1),
            activa=True,
        )
        db.session.add(promocion)
        db.session.flush()
        db.session.add(TiendaPromocionGastronomiaProducto(
            id_promocion=promocion.id_promocion,
            id_producto=producto_id,
        ))
        db.session.commit()

    response = client.get('/api/gastronomia/public/menu-tv/resto-tv-promo')

    assert response.status_code == 200
    producto = response.get_json()['categorias'][0]['productos'][0]
    assert producto['precio'] == 20000
    assert producto['precio_anterior'] == 25000
    assert producto['promocion_activa']['etiqueta'] == '-20%'


def test_menu_tv_config_guarda_modo_rotacion():
    app = create_app('testing')
    client = app.test_client()
    _crear_base(app, 'Resto TV Config', 'resto_tv_config', 'resto-tv-config')
    _loguear(client, app, 'resto_tv_config')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))

    response = client.put(
        '/api/gastronomia/menu-tv/config',
        json={
            'menu_tv_publico_activo': True,
            'menu_tv_titulo': 'Carta nocturna',
            'menu_tv_tema': 'clasico',
            'menu_tv_modo_rotacion': 'slides',
            'menu_tv_mostrar_precios': True,
            'menu_tv_intervalo_refresco_seg': 45,
        },
        headers={'X-CSRFToken': csrf},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data['config']['modo_rotacion'] == 'slides'

    invalido = client.put(
        '/api/gastronomia/menu-tv/config',
        json={
            'menu_tv_publico_activo': True,
            'menu_tv_modo_rotacion': 'teatro-laser',
        },
        headers={'X-CSRFToken': csrf},
    )
    assert invalido.status_code == 200
    assert invalido.get_json()['config']['modo_rotacion'] == 'auto'
