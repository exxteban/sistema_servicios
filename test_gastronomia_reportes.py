import re
from datetime import date

from app import create_app, db
from app.models import Caja, Cliente, SesionCaja, Usuario
from gastronomia.models import GastronomiaCategoria, GastronomiaClienteConfig, GastronomiaProducto


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


def _crear_productos(app, nombre_cliente: str, username: str):
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
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Reportes')
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
        pizza = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Pizza',
            precio=40000,
        )
        bebida = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Bebida',
            precio=10000,
        )
        db.session.add_all([pizza, bebida])
        db.session.commit()
        return cliente.id_cliente, pizza.id_producto, bebida.id_producto


def _abrir_caja(app, username: str):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        assert usuario is not None
        caja = Caja(nombre=f'Caja {username}', ubicacion='Gastronomia')
        db.session.add(caja)
        db.session.flush()
        db.session.add(SesionCaja(
            id_caja=caja.id_caja,
            id_usuario=usuario.id_usuario,
            monto_inicial=0,
            estado='abierta',
        ))
        db.session.commit()


def _pedido_cobrado(client, csrf, items, metodo_pago='efectivo', descuento=0):
    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={'tipo_pedido': 'mostrador', 'items': items},
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
    listo_resp = client.post(
        f'/api/gastronomia/cocina/pedidos/{pedido_id}/listo',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert listo_resp.status_code == 200
    cobrar_resp = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': metodo_pago, 'descuento_monto': descuento},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200
    return pedido_id


def test_reportes_resumen_filtra_cliente_y_calcula_metricas():
    app = create_app('testing')
    client_uno = app.test_client()
    client_dos = app.test_client()
    _cliente_uno_id, pizza_uno_id, bebida_uno_id = _crear_productos(app, 'Resto Reporte A', 'resto_reporte_a')
    _cliente_dos_id, pizza_dos_id, _bebida_dos_id = _crear_productos(app, 'Resto Reporte B', 'resto_reporte_b')

    _loguear(client_uno, app, 'resto_reporte_a')
    _abrir_caja(app, 'resto_reporte_a')
    csrf_uno = _csrf(client_uno.get('/gastronomia/caja').get_data(as_text=True))
    _pedido_cobrado(
        client_uno,
        csrf_uno,
        [{'producto_id': pizza_uno_id, 'cantidad': 2}, {'producto_id': bebida_uno_id, 'cantidad': 1}],
        metodo_pago='efectivo',
        descuento=5000,
    )
    _pedido_cobrado(
        client_uno,
        csrf_uno,
        [{'producto_id': bebida_uno_id, 'cantidad': 3}],
        metodo_pago='tarjeta',
    )

    _loguear(client_dos, app, 'resto_reporte_b')
    _abrir_caja(app, 'resto_reporte_b')
    csrf_dos = _csrf(client_dos.get('/gastronomia/caja').get_data(as_text=True))
    _pedido_cobrado(client_dos, csrf_dos, [{'producto_id': pizza_dos_id, 'cantidad': 1}], metodo_pago='qr')

    fecha = date.today().isoformat()
    response = client_uno.get('/api/gastronomia/reportes/resumen', query_string={'desde': fecha, 'hasta': fecha})
    assert response.status_code == 200
    resumen = response.get_json()['resumen']
    assert resumen['pedidos_cobrados'] == 2
    assert resumen['ventas_total'] == 115000
    assert resumen['descuentos_total'] == 5000
    assert resumen['ticket_promedio'] == 57500
    assert resumen['pedidos_cancelados'] == 0
    assert resumen['tiempo_promedio_preparacion_min'] >= 0
    assert {item['metodo_pago']: item['total'] for item in resumen['ventas_por_metodo']} == {
        'efectivo': 85000,
        'tarjeta': 30000,
    }
    productos = {item['nombre_producto']: item for item in resumen['productos_mas_vendidos']}
    assert productos['Bebida']['cantidad'] == 4
    assert productos['Pizza']['cantidad'] == 2
    assert 'qr' not in {item['metodo_pago'] for item in resumen['ventas_por_metodo']}


def test_reportes_page_carga_para_cliente_gastronomico():
    app = create_app('testing')
    client = app.test_client()
    _crear_productos(app, 'Resto Reporte Page', 'resto_reporte_page')
    _loguear(client, app, 'resto_reporte_page')

    response = client.get('/gastronomia/reportes')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Reportes' in html
    assert 'js/reportes.js' in html
