import re

from app import create_app, db
from app.models import Caja, Cliente, Permiso, Rol, SesionCaja, Usuario
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaMesa,
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
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Salon')
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
            nombre='Pizza',
            precio=45000,
        )
        db.session.add(producto)
        db.session.commit()
        return cliente.id_cliente, producto.id_producto


def _crear_pedido_mesa(client, csrf, producto_id, mesa):
    response = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mesa',
            'mesa': mesa,
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 201
    return response.get_json()['pedido']['id_pedido']


def _crear_usuario_con_permisos(cliente_id: int, username: str, codigos: list[str]) -> None:
    rol = Rol(nombre=f'Rol {username}', descripcion='Rol de prueba gastronomia', nivel_jerarquia=1)
    permisos = Permiso.query.filter(Permiso.codigo.in_(codigos)).all()
    assert {permiso.codigo for permiso in permisos} == set(codigos)
    rol.permisos.extend(permisos)
    db.session.add(rol)
    db.session.flush()
    usuario = Usuario(
        id_cliente=cliente_id,
        username=username,
        nombre_completo=f'Usuario {username}',
        id_rol=rol.id_rol,
        activo=True,
    )
    usuario.set_password('clave123')
    db.session.add(usuario)


def test_salon_crea_mesas_y_calcula_estado_desde_pedidos():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Salon Uno', 'resto_salon_uno')
    _loguear(client, app, 'resto_salon_uno')

    dashboard = client.get('/gastronomia/')
    assert dashboard.status_code == 200
    dashboard_html = dashboard.get_data(as_text=True)
    assert 'Menu operativo' in dashboard_html
    assert 'Carga y configuracion' in dashboard_html
    assert 'Cargar menu' in dashboard_html
    assert 'Configurar salon' in dashboard_html

    page = client.get('/gastronomia/salon')
    assert page.status_code == 200
    page_html = page.get_data(as_text=True)
    assert 'Salon' in page_html
    assert 'Configurar mesas' in page_html
    assert 'move-table-grid' in page_html
    csrf = _csrf(page_html)

    salon_config = client.get('/gastronomia/salon/configuracion')
    assert salon_config.status_code == 200
    assert 'Alta y mantenimiento de mesas fuera del flujo operativo.' in salon_config.get_data(as_text=True)

    mesa_resp = client.post(
        '/api/gastronomia/salon/mesas',
        json={'nombre': 'M1', 'capacidad': 4, 'ubicacion': 'Terraza'},
        headers={'X-CSRFToken': csrf},
    )
    assert mesa_resp.status_code == 201
    mesa_id = mesa_resp.get_json()['mesa']['id_mesa']

    salon_vacio = client.get('/api/gastronomia/salon/estado').get_json()['mesas']
    assert salon_vacio[0]['estado_salon'] == 'libre'
    pedido_id = _crear_pedido_mesa(client, csrf, producto_id, 'M1')

    salon_ocupado = client.get('/api/gastronomia/salon/estado').get_json()['mesas']
    assert salon_ocupado[0]['pedido_activo']['id_pedido'] == pedido_id
    assert [pedido['id_pedido'] for pedido in salon_ocupado[0]['pedidos_activos']] == [pedido_id]
    assert salon_ocupado[0]['pedidos_activos_count'] == 1
    assert salon_ocupado[0]['estado_salon'] == 'ocupada'

    client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/estado',
        json={'estado': 'preparando'},
        headers={'X-CSRFToken': csrf},
    )
    salon_cocina = client.get('/api/gastronomia/salon/estado').get_json()['mesas']
    assert salon_cocina[0]['estado_salon'] == 'esperando_cocina'

    pos_prefill = client.get('/gastronomia/pos', query_string={'mesa': 'M1'}).get_data(as_text=True)
    assert 'data-mesa-inicial="M1"' in pos_prefill
    assert 'data-order-type="mesa"' in pos_prefill
    assert 'id="table-grid"' in pos_prefill
    assert 'id="table-name"' in pos_prefill
    with app.app_context():
        mesa = GastronomiaMesa.query.filter_by(cliente_id=cliente_id, id_mesa=mesa_id).first()
        assert mesa.nombre == 'M1'


def test_pedidos_de_mesa_validan_mesa_activa_y_salon_muestra_duplicados():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id = _crear_producto(app, 'Resto Salon Validacion', 'resto_salon_validacion')
    _loguear(client, app, 'resto_salon_validacion')
    csrf = _csrf(client.get('/gastronomia/salon').get_data(as_text=True))

    inexistente = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mesa',
            'mesa': 'Fantasma',
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert inexistente.status_code == 400
    assert 'Mesa no encontrada' in inexistente.get_json()['mensaje']

    client.post(
        '/api/gastronomia/salon/mesas',
        json={'nombre': 'D1', 'activo': False},
        headers={'X-CSRFToken': csrf},
    )
    inactiva = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mesa',
            'mesa': 'D1',
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert inactiva.status_code == 400

    client.post('/api/gastronomia/salon/mesas', json={'nombre': 'M2'}, headers={'X-CSRFToken': csrf})
    pedido_uno_id = _crear_pedido_mesa(client, csrf, producto_id, 'M2')
    pedido_dos_id = _crear_pedido_mesa(client, csrf, producto_id, 'M2')

    mesas = client.get('/api/gastronomia/salon/estado').get_json()['mesas']
    mesa = next(item for item in mesas if item['nombre'] == 'M2')
    assert mesa['pedidos_activos_count'] == 2
    assert [pedido['id_pedido'] for pedido in mesa['pedidos_activos']] == [pedido_dos_id, pedido_uno_id]
    assert mesa['pedido_activo']['id_pedido'] == pedido_dos_id


def test_pos_puede_listar_mesas_sin_permiso_de_administrar_salon():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, _producto_id = _crear_producto(app, 'Resto POS Mesas', 'resto_pos_mesas_admin')
    with app.app_context():
        db.session.add(GastronomiaMesa(cliente_id=cliente_id, nombre='P1', capacidad=2))
        _crear_usuario_con_permisos(
            cliente_id,
            'resto_pos_mesas',
            ['gastronomia_acceso', 'gastronomia_pos'],
        )
        db.session.commit()

    _loguear(client, app, 'resto_pos_mesas')
    pos_page = client.get('/gastronomia/pos')
    assert pos_page.status_code == 200
    pos_html = pos_page.get_data(as_text=True)
    csrf = _csrf(pos_html)
    assert 'pos_table_warnings.js' in pos_html

    mesas_resp = client.get('/api/gastronomia/salon/mesas')
    assert mesas_resp.status_code == 200
    mesas = mesas_resp.get_json()['mesas']
    assert [mesa['nombre'] for mesa in mesas] == ['P1']

    estado_resp = client.get('/api/gastronomia/salon/estado')
    assert estado_resp.status_code == 200
    estado_mesas = estado_resp.get_json()['mesas']
    assert estado_mesas[0]['nombre'] == 'P1'
    assert estado_mesas[0]['estado_salon'] == 'libre'

    crear_resp = client.post(
        '/api/gastronomia/salon/mesas',
        json={'nombre': 'P2'},
        headers={'X-CSRFToken': csrf},
    )
    assert crear_resp.status_code == 403


def test_salon_mueve_pedido_y_respeta_cliente():
    app = create_app('testing')
    client_uno = app.test_client()
    client_dos = app.test_client()
    cliente_uno_id, producto_uno_id = _crear_producto(app, 'Resto Salon A', 'resto_salon_a')
    _cliente_dos_id, producto_dos_id = _crear_producto(app, 'Resto Salon B', 'resto_salon_b')

    _loguear(client_uno, app, 'resto_salon_a')
    csrf_uno = _csrf(client_uno.get('/gastronomia/salon').get_data(as_text=True))
    for nombre in ('A1', 'A2'):
        client_uno.post('/api/gastronomia/salon/mesas', json={'nombre': nombre}, headers={'X-CSRFToken': csrf_uno})
    pedido_uno_id = _crear_pedido_mesa(client_uno, csrf_uno, producto_uno_id, 'A1')

    mover_resp = client_uno.post(
        f'/api/gastronomia/salon/pedidos/{pedido_uno_id}/mover',
        json={'mesa': 'A2'},
        headers={'X-CSRFToken': csrf_uno},
    )
    assert mover_resp.status_code == 200
    assert mover_resp.get_json()['pedido']['mesa'] == 'A2'

    _loguear(client_dos, app, 'resto_salon_b')
    csrf_dos = _csrf(client_dos.get('/gastronomia/salon').get_data(as_text=True))
    client_dos.post('/api/gastronomia/salon/mesas', json={'nombre': 'B1'}, headers={'X-CSRFToken': csrf_dos})
    _pedido_dos_id = _crear_pedido_mesa(client_dos, csrf_dos, producto_dos_id, 'B1')
    ajeno_resp = client_dos.post(
        f'/api/gastronomia/salon/pedidos/{pedido_uno_id}/mover',
        json={'mesa': 'B1'},
        headers={'X-CSRFToken': csrf_dos},
    )
    assert ajeno_resp.status_code == 404

    with app.app_context():
        pedido = GastronomiaPedido.query.filter_by(cliente_id=cliente_uno_id, id_pedido=pedido_uno_id).first()
        assert pedido.mesa == 'A2'
        evento = GastronomiaPedidoEvento.query.filter_by(
            cliente_id=cliente_uno_id,
            pedido_id=pedido_uno_id,
            tipo='pedido_mesa_movido',
        ).first()
        assert evento is not None


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


def test_salon_expone_permisos_para_acciones_de_pedido():
    app = create_app('testing')
    client = app.test_client()
    _crear_producto(app, 'Resto Salon Permisos', 'resto_salon_permisos')
    _loguear(client, app, 'resto_salon_permisos')

    page_html = client.get('/gastronomia/salon').get_data(as_text=True)
    assert 'data-puede-cobrar="1"' in page_html
    assert 'data-puede-editar-pedido="1"' in page_html


def test_salon_mantiene_mesa_pagada_hasta_liberarla():
    app = create_app('testing')
    client = app.test_client()
    _crear_producto(app, 'Resto Salon Cobro', 'resto_salon_cobro')
    _loguear(client, app, 'resto_salon_cobro')
    _abrir_caja(app, 'resto_salon_cobro')

    csrf = _csrf(client.get('/gastronomia/salon').get_data(as_text=True))
    client.post('/api/gastronomia/salon/mesas', json={'nombre': 'C1'}, headers={'X-CSRFToken': csrf})
    pedido_id = _crear_pedido_mesa(client, csrf, _producto_id(app, 'resto_salon_cobro'), 'C1')

    # Llevar el pedido a un estado activo posterior a "abierto" (enviado a cocina).
    enviar = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/enviar-cocina',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert enviar.status_code == 200

    mesas = client.get('/api/gastronomia/salon/estado').get_json()['mesas']
    mesa = next(item for item in mesas if item['nombre'] == 'C1')
    assert mesa['pedidos_activos_count'] == 1
    assert mesa['estado_salon'] == 'esperando_cocina'

    # Una vez cobrado, sigue figurando en el salon para evitar reutilizar la mesa antes de liberarla.
    cobrar = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar.status_code == 200

    mesas_despues = client.get('/api/gastronomia/salon/estado').get_json()['mesas']
    mesa_despues = next(item for item in mesas_despues if item['nombre'] == 'C1')
    assert mesa_despues['pedidos_activos_count'] == 1
    assert mesa_despues['pedido_activo']['id_pedido'] == pedido_id
    assert mesa_despues['pedido_activo']['pagado'] is True
    assert mesa_despues['pedido_activo']['items'][0]['nombre_producto'] == 'Pizza'
    assert mesa_despues['estado_salon'] == 'pagada'

    liberar = client.post(
        f'/api/gastronomia/salon/pedidos/{pedido_id}/liberar-mesa',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert liberar.status_code == 200

    mesas_liberadas = client.get('/api/gastronomia/salon/estado').get_json()['mesas']
    mesa_liberada = next(item for item in mesas_liberadas if item['nombre'] == 'C1')
    assert mesa_liberada['pedidos_activos_count'] == 0
    assert mesa_liberada['pedido_activo'] is None
    assert mesa_liberada['estado_salon'] == 'libre'

    with app.app_context():
        pedido = GastronomiaPedido.query.get(pedido_id)
        assert pedido.estado == 'cobrado'

    liberar_otra_vez = client.post(
        f'/api/gastronomia/salon/pedidos/{pedido_id}/liberar-mesa',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert liberar_otra_vez.status_code == 400


def test_salon_no_libera_mesa_con_pedido_sin_cobrar():
    app = create_app('testing')
    client = app.test_client()
    _crear_producto(app, 'Resto Salon Sin Cobro', 'resto_salon_sin_cobro')
    _loguear(client, app, 'resto_salon_sin_cobro')

    csrf = _csrf(client.get('/gastronomia/salon').get_data(as_text=True))
    client.post('/api/gastronomia/salon/mesas', json={'nombre': 'S1'}, headers={'X-CSRFToken': csrf})
    pedido_id = _crear_pedido_mesa(client, csrf, _producto_id(app, 'resto_salon_sin_cobro'), 'S1')

    liberar = client.post(
        f'/api/gastronomia/salon/pedidos/{pedido_id}/liberar-mesa',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert liberar.status_code == 400

    mesas_despues = client.get('/api/gastronomia/salon/estado').get_json()['mesas']
    mesa_despues = next(item for item in mesas_despues if item['nombre'] == 'S1')
    assert mesa_despues['pedidos_activos_count'] == 1
    assert mesa_despues['estado_salon'] == 'ocupada'


def _producto_id(app, username: str) -> int:
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        producto = GastronomiaProducto.query.filter_by(cliente_id=usuario.id_cliente).first()
        return producto.id_producto
