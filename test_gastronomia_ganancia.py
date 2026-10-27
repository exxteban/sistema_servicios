from datetime import date

from app import create_app, db
from app.models import MovimientoCaja, SesionCaja, Usuario
from gastronomia.models import GastronomiaProducto
from test_gastronomia_reportes import _abrir_caja, _crear_insumo_receta, _crear_productos, _csrf, _loguear, _pedido_cobrado


def test_costo_plato_suma_insumos_y_extra_y_aplica_a_categoria():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, pizza_id, bebida_id = _crear_productos(app, 'Resto Costos', 'resto_costos')
    insumo_id = _crear_insumo_receta(app, cliente_id, pizza_id, nombre='Muzza Costos', stock=10, cantidad=2)
    _loguear(client, app, 'resto_costos')
    _abrir_caja(app, 'resto_costos')
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    headers = {'X-CSRFToken': csrf}

    resp = client.put(f'/api/gastronomia/stock/insumos/{insumo_id}/precio-compra', json={'precio_compra': 5000}, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()['insumo']['precio_compra'] == 5000

    resp = client.put(
        f'/api/gastronomia/stock/productos/{pizza_id}/costo-extra',
        json={'monto': 2000, 'aplicar_categoria': True},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['actualizados'] == 2
    costo = data['costo']
    assert costo['costo_insumos'] == 10000
    assert costo['costo_extra'] == 2000
    assert costo['costo_total'] == 12000
    assert costo['ganancia'] == 28000
    assert costo['ganancia_pct'] == 70.0
    assert costo['insumos'][0]['subtotal'] == 10000

    resumen = client.get('/api/gastronomia/stock/costos/resumen').get_json()['productos']
    por_id = {item['producto_id']: item for item in resumen}
    assert por_id[bebida_id]['costo_total'] == 2000

    resp = client.put(f'/api/gastronomia/stock/productos/{pizza_id}/costo-extra', json={'monto': -1}, headers=headers)
    assert resp.status_code == 400


def test_ganancia_estimada_por_dia_resta_costo_y_gastos():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, pizza_id, bebida_id = _crear_productos(app, 'Resto Ganancia', 'resto_ganancia')
    _crear_insumo_receta(app, cliente_id, pizza_id, nombre='Muzza Ganancia', stock=10, cantidad=1, precio_compra=10000)
    with app.app_context():
        pizza = db.session.get(GastronomiaProducto, pizza_id)
        pizza.costo_extra = 2000
        db.session.commit()

    _loguear(client, app, 'resto_ganancia')
    _abrir_caja(app, 'resto_ganancia')
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    _pedido_cobrado(
        client,
        csrf,
        [{'producto_id': pizza_id, 'cantidad': 2}, {'producto_id': bebida_id, 'cantidad': 1}],
    )

    with app.app_context():
        usuario = Usuario.query.filter_by(username='resto_ganancia').first()
        sesion = SesionCaja.query.filter_by(id_usuario=usuario.id_usuario, estado='abierta').first()
        db.session.add(MovimientoCaja(
            id_sesion_caja=sesion.id_sesion,
            id_usuario=usuario.id_usuario,
            tipo='egreso',
            monto=5000,
            motivo='Garrafa de gas',
        ))
        db.session.commit()

    hoy = date.today().isoformat()
    resp = client.get('/api/gastronomia/reportes/ganancia', query_string={'desde': hoy, 'hasta': hoy})
    assert resp.status_code == 200
    data = resp.get_json()['ganancia']
    totales = data['totales']
    assert totales['ventas'] == 90000
    assert totales['costo'] == 24000
    assert totales['ganancia_bruta'] == 66000
    assert totales['gastos'] == 5000
    assert totales['ganancia_neta'] == 61000
    assert totales['unidades_sin_costo'] == 1
    assert len(data['dias']) == 1
    assert [item['nombre'] for item in data['platos_sin_costo']] == ['Bebida']
    pizza = next(item for item in data['platos'] if item['producto_id'] == pizza_id)
    assert pizza['ganancia'] == 56000
