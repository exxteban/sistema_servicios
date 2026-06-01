from app import create_app, db
from app.models import MovimientoStock, Producto
from gastronomia.models import GastronomiaProducto
from test_gastronomia_pedidos import _agregar_insumo, _crear_menu_para_pedidos, _csrf, _loguear


def test_previsualizacion_receta_alerta_antes_de_guardar_sin_mutar_stock():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id, _opcion_id = _crear_menu_para_pedidos(
        app,
        'Resto Preview Receta',
        'resto_preview_receta',
    )
    insumo_id = _agregar_insumo(app, cliente_id, 'Medallon preview', 1)
    _loguear(client, app, 'resto_preview_receta')
    pos_html = client.get('/gastronomia/pos').get_data(as_text=True)
    csrf = _csrf(pos_html)
    assert 'js/pos_stock_alerts.js' in pos_html
    assert 'js/pos_channel_prices.js' in pos_html
    assert pos_html.index('js/pos_channel_prices.js') < pos_html.index('js/pos.js')
    assert 'css/pos.css' in pos_html
    assert client.get('/gastronomia/static/css/pos.css').status_code == 200
    stock_script = client.get('/gastronomia/static/js/pos_stock_alerts.js')
    channel_prices_script = client.get('/gastronomia/static/js/pos_channel_prices.js')
    assert stock_script.status_code == 200
    assert channel_prices_script.status_code == 200
    assert '/api/gastronomia/stock/previsualizar-pedido' in stock_script.get_data(as_text=True)
    assert 'fetchProducts' in channel_prices_script.get_data(as_text=True)
    pos_script = client.get('/gastronomia/static/js/pos.js')
    assert 'window.GastronomiaStockAlerts?.refresh(cart);' in pos_script.get_data(as_text=True)

    assert client.put(
        f'/api/gastronomia/stock/productos/{producto_id}/receta',
        json={'items': [{'insumo_id': insumo_id, 'cantidad': 1}]},
        headers={'X-CSRFToken': csrf},
    ).status_code == 200

    response = client.post(
        '/api/gastronomia/stock/previsualizar-pedido',
        json={'items': [
            {'producto_id': producto_id, 'cantidad': 1},
            {'producto_id': producto_id, 'cantidad': 1},
        ]},
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 200
    assert response.get_json()['alertas'] == [{
        'cantidad': 2,
        'faltante': 1,
        'mensaje': 'Stock insuficiente de "Medallon preview": requiere 2, disponible 1.',
        'nombre': 'Medallon preview',
        'stock_actual': 1,
        'tipo_origen': 'receta',
    }]
    with app.app_context():
        assert db.session.get(Producto, insumo_id).stock_actual == 1
        assert MovimientoStock.query.filter_by(id_producto=insumo_id).count() == 0


def test_previsualizacion_alerta_sin_receta_y_stock_directo_sin_bloquear():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id, _opcion_id = _crear_menu_para_pedidos(
        app,
        'Resto Preview Directo',
        'resto_preview_directo',
    )
    _loguear(client, app, 'resto_preview_directo')
    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))

    sin_receta = client.post(
        '/api/gastronomia/stock/previsualizar-pedido',
        json={'items': [{'producto_id': producto_id, 'cantidad': 1}]},
        headers={'X-CSRFToken': csrf},
    )
    assert sin_receta.status_code == 200
    assert sin_receta.get_json()['alertas'][0]['tipo_origen'] == 'sin_receta'

    with app.app_context():
        producto = db.session.get(GastronomiaProducto, producto_id)
        producto.control_stock_venta = True
        producto.stock_disponible = 1
        db.session.commit()

    stock_directo = client.post(
        '/api/gastronomia/stock/previsualizar-pedido',
        json={'items': [{'producto_id': producto_id, 'cantidad': 2}]},
        headers={'X-CSRFToken': csrf},
    )
    assert stock_directo.status_code == 200
    alerta = stock_directo.get_json()['alertas'][0]
    assert alerta['tipo_origen'] == 'producto_menu'
    assert alerta['faltante'] == 1
    with app.app_context():
        assert db.session.get(GastronomiaProducto, producto_id).stock_disponible == 1
