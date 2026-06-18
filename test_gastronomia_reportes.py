import re
from datetime import date, datetime, time, timedelta

from app import create_app, db
from app.models import Caja, Categoria, Cliente, MovimientoCaja, Producto, SesionCaja, Usuario, Venta
from gastronomia.models import GastronomiaCategoria, GastronomiaClienteConfig, GastronomiaPedido, GastronomiaPedidoPago, GastronomiaProducto
from gastronomia.stock_models import GastronomiaRecetaInsumo
from gastronomia.services.inteligencia_service import obtener_inteligencia_gastronomia


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


def _crear_insumo_receta(app, cliente_id, producto_id, nombre='Queso BI', stock=2, cantidad=1, precio_compra=0):
    with app.app_context():
        categoria = Categoria.query.filter_by(nombre='Insumos BI').first()
        if not categoria:
            categoria = Categoria(nombre='Insumos BI')
            db.session.add(categoria)
            db.session.flush()
        insumo = Producto(
            codigo=f'INS-{nombre.upper().replace(" ", "-")}',
            nombre=nombre,
            id_categoria=categoria.id_categoria,
            id_cliente=cliente_id,
            precio_compra=precio_compra,
            precio_venta=0,
            stock_actual=stock,
            unidad_stock='unidad',
        )
        db.session.add(insumo)
        db.session.flush()
        db.session.add(GastronomiaRecetaInsumo(
            cliente_id=cliente_id,
            producto_id=producto_id,
            insumo_id=insumo.id_producto,
            cantidad=cantidad,
        ))
        db.session.commit()
        return insumo.id_producto


def _pedido_cobrado(client, csrf, items, metodo_pago='efectivo', descuento=0, pedido_extra=None):
    payload = {'tipo_pedido': 'mostrador', 'items': items}
    if pedido_extra:
        payload.update(pedido_extra)
    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json=payload,
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
        json={
            'metodo_pago': metodo_pago,
            'descuento_monto': descuento,
            'referencia': 'REF-TEST' if metodo_pago != 'efectivo' else '',
        },
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200
    return pedido_id


def _mover_pago_pedido(app, pedido_id, hora):
    with app.app_context():
        pago = GastronomiaPedidoPago.query.filter_by(pedido_id=pedido_id).first()
        assert pago is not None
        pago.fecha_pago = datetime.combine(date.today(), time(hour=hora))
        db.session.commit()


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
    assert 'Ventas cobradas para anular' in html
    assert 'Exportar CSV' in html


def test_reportes_exporta_csv_simple_del_periodo():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, pizza_id, bebida_id = _crear_productos(app, 'Resto Reporte CSV', 'resto_reporte_csv')
    _loguear(client, app, 'resto_reporte_csv')
    _abrir_caja(app, 'resto_reporte_csv')
    csrf = _csrf(client.get('/gastronomia/reportes').get_data(as_text=True))
    _pedido_cobrado(
        client,
        csrf,
        [{'producto_id': pizza_id, 'cantidad': 1}, {'producto_id': bebida_id, 'cantidad': 2}],
        metodo_pago='qr',
    )

    fecha = date.today().isoformat()
    response = client.get('/api/gastronomia/reportes/exportar.csv', query_string={'desde': fecha, 'hasta': fecha})
    assert response.status_code == 200
    assert 'text/csv' in response.headers.get('Content-Type', '')
    assert f'gastronomia_reportes_{fecha}_a_{fecha}.csv' in response.headers.get('Content-Disposition', '')
    content = response.get_data(as_text=True)
    assert 'Reporte,Gastronomia' in content
    assert 'Productos mas vendidos' in content
    assert 'Ventas por metodo' in content
    assert 'Ventas anulables' in content
    assert 'Pizza' in content
    assert 'qr' in content


def test_inteligencia_gastronomia_calcula_metricas_accionables():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, pizza_id, bebida_id = _crear_productos(app, 'Resto BI Gastro', 'resto_bi_gastro')
    _loguear(client, app, 'resto_bi_gastro')
    _abrir_caja(app, 'resto_bi_gastro')
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    _crear_insumo_receta(app, cliente_id, bebida_id, stock=2, cantidad=1)
    _crear_insumo_receta(app, cliente_id, pizza_id, nombre='Harina BI', stock=30, cantidad=1, precio_compra=1000)
    _crear_insumo_receta(app, cliente_id, bebida_id, nombre='Bebida Costo BI', stock=30, cantidad=1, precio_compra=9000)

    pedido_uno = _pedido_cobrado(
        client,
        csrf,
        [{'producto_id': pizza_id, 'cantidad': 2}, {'producto_id': bebida_id, 'cantidad': 1}],
        pedido_extra={'nombre_cliente': 'Ana Gastro', 'celular_cliente': '0981123456'},
    )
    pedido_dos = _pedido_cobrado(
        client,
        csrf,
        [{'producto_id': bebida_id, 'cantidad': 3}],
        pedido_extra={'nombre_cliente': 'Ana Gastro', 'celular_cliente': '0981123456'},
    )
    pedido_tres = _pedido_cobrado(client, csrf, [{'producto_id': pizza_id, 'cantidad': 1}])
    pedido_cuatro = _pedido_cobrado(client, csrf, [{'producto_id': pizza_id, 'cantidad': 1}])
    pedido_cinco = _pedido_cobrado(client, csrf, [{'producto_id': pizza_id, 'cantidad': 1}])
    pedido_seis = _pedido_cobrado(client, csrf, [{'producto_id': bebida_id, 'cantidad': 1}])
    for pedido_id, hora in (
        (pedido_uno, 10),
        (pedido_tres, 10),
        (pedido_cuatro, 10),
        (pedido_dos, 11),
        (pedido_cinco, 12),
        (pedido_seis, 13),
    ):
        _mover_pago_pedido(app, pedido_id, hora)

    hoy = date.today()
    ayer = hoy - timedelta(days=1)
    with app.app_context():
        panel = obtener_inteligencia_gastronomia(
            {'desde': hoy, 'hasta': hoy},
            {'desde': ayer, 'hasta': ayer},
            cliente_id,
        )

    assert panel['activo'] is True
    assert panel['resumen']['pedidos_cobrados'] == 6
    assert panel['resumen']['ventas_total'] == 250000
    productos = {item['nombre']: item for item in panel['productos_top']}
    assert productos['Bebida']['cantidad'] == 5
    assert productos['Pizza']['cantidad'] == 5
    assert panel['canales'][0]['canal'] == 'mostrador'
    assert panel['canales'][0]['pedidos'] == 6
    assert panel['stock_menu_alertas'][0]['nombre'] == 'Queso BI'
    assert 'dura' in panel['stock_menu_alertas'][0]['mensaje']
    assert panel['promos_horario_bajo']
    assert all(item['pedidos'] <= item['promedio_pedidos'] for item in panel['promos_horario_bajo'])
    assert panel['productos_bajo_margen'][0]['nombre'] == 'Bebida'
    assert panel['productos_bajo_margen'][0]['margen_pct'] == 10.0
    assert panel['clientes_frecuentes'][0]['nombre'] == 'Ana Gastro'
    assert panel['clientes_frecuentes'][0]['pedidos'] == 2
    assert panel['insights']

    response = client.get('/inteligencia', query_string={'vista': 'gastronomia'})
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Gastronomía' in html
    assert 'Productos más vendidos' in html
    assert 'Stock conectado al menú' in html
    assert 'Horarios flojos para empujar venta' in html
    assert 'Alto volumen con bajo margen' in html
    assert 'Clientes frecuentes gastronómicos' in html
    assert 'Bebida' in html


def test_reportes_anula_venta_gastronomica_y_actualiza_stock_caja_metricas():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, pizza_id, _bebida_id = _crear_productos(app, 'Resto Reporte Anula', 'resto_reporte_anula')
    _loguear(client, app, 'resto_reporte_anula')
    _abrir_caja(app, 'resto_reporte_anula')
    page = client.get('/gastronomia/reportes')
    csrf = _csrf(page.get_data(as_text=True))

    with app.app_context():
        producto = GastronomiaProducto.query.get(pizza_id)
        producto.control_stock_venta = True
        producto.stock_disponible = 3
        db.session.commit()

    pedido_id = _pedido_cobrado(client, csrf, [{'producto_id': pizza_id, 'cantidad': 2}])
    fecha = date.today().isoformat()
    resumen_resp = client.get('/api/gastronomia/reportes/resumen', query_string={'desde': fecha, 'hasta': fecha})
    assert resumen_resp.status_code == 200
    venta_item = resumen_resp.get_json()['resumen']['ventas_anulables'][0]
    assert venta_item['id_pedido'] == pedido_id
    assert venta_item['total_cobrado'] == 80000

    anular_resp = client.post(
        f'/api/gastronomia/reportes/pedidos/{pedido_id}/anular-venta',
        json={'motivo': 'Error de carga'},
        headers={'X-CSRFToken': csrf},
    )
    assert anular_resp.status_code == 200
    assert anular_resp.get_json()['pedido']['estado'] == 'cancelado'

    with app.app_context():
        pedido = GastronomiaPedido.query.get(pedido_id)
        producto = GastronomiaProducto.query.get(pizza_id)
        assert pedido.estado == 'cancelado'
        assert GastronomiaPedidoPago.query.filter_by(cliente_id=cliente_id, pedido_id=pedido_id).count() == 0
        assert producto.stock_disponible == 3
        venta = Venta.query.get(venta_item['id_venta'])
        assert venta.estado == 'anulada'
        assert 'Error de carga' in venta.observaciones
        reverso = MovimientoCaja.query.filter_by(
            referencia_tipo='anulacion_venta',
            referencia_id=venta.id_venta,
            tipo='egreso',
        ).first()
        assert reverso is not None
        assert float(reverso.monto) == 80000

    resumen_post = client.get('/api/gastronomia/reportes/resumen', query_string={'desde': fecha, 'hasta': fecha})
    resumen = resumen_post.get_json()['resumen']
    assert resumen['pedidos_cobrados'] == 0
    assert resumen['ventas_total'] == 0
    assert resumen['pedidos_cancelados'] == 1
    assert resumen['ventas_anulables'] == []
