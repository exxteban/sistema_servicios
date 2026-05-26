import re

from app import create_app, db
from app.models import Cliente, Usuario
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaGrupoOpciones,
    GastronomiaOpcionProducto,
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


def test_pos_page_carga_y_pedido_se_guarda_con_totales_backend():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id, opcion_id = _crear_menu_para_pedidos(app)
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
