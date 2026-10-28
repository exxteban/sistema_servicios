from datetime import date

from app import create_app, db
from app.models import MovimientoCaja, SesionCaja, Usuario
from app.models.caja import REFERENCIA_COMPRA_INSUMOS
from control_de_empleados.models import Empleado, EmpleadoPago
from gastos_corrientes.models import GastoCorriente, PagoGastoCorriente
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
        db.session.add(MovimientoCaja(
            id_sesion_caja=sesion.id_sesion,
            id_usuario=usuario.id_usuario,
            tipo='egreso',
            monto=7000,
            motivo='Verduras del dia',
            referencia_tipo=REFERENCIA_COMPRA_INSUMOS,
        ))
        empleado = Empleado(cliente_id=cliente_id, nombre_completo='Cocinero Ganancia', salario_base=3000)
        gasto = GastoCorriente(cliente_id=cliente_id, nombre='Luz Ganancia', monto_estimado=2000)
        db.session.add_all([empleado, gasto])
        db.session.flush()
        db.session.add_all([
            EmpleadoPago(
                cliente_id=cliente_id,
                id_empleado=empleado.id_empleado,
                periodo=date.today().strftime('%Y-%m'),
                fecha_pago=date.today(),
                total_pagado=3000,
            ),
            PagoGastoCorriente(
                cliente_id=cliente_id,
                id_gasto_corriente=gasto.id_gasto_corriente,
                periodo_anio=date.today().year,
                periodo_mes=date.today().month,
                fecha_vencimiento=date.today(),
                fecha_pago=date.today(),
                monto_pagado=2000,
                estado='pagado',
            ),
        ])
        db.session.commit()

    hoy = date.today().isoformat()
    resp = client.get('/api/gastronomia/reportes/ganancia', query_string={'desde': hoy, 'hasta': hoy})
    assert resp.status_code == 200
    data = resp.get_json()['ganancia']
    totales = data['totales']
    assert totales['ventas'] == 90000
    assert totales['costo'] == 24000
    assert totales['ganancia_bruta'] == 66000
    assert totales['gastos_caja'] == 5000
    assert totales['gastos_fijos'] == 2000
    assert totales['sueldos'] == 3000
    assert totales['gastos'] == 10000
    assert totales['insumos_caja'] == 7000
    assert totales['ganancia_neta'] == 56000
    detalle = {(item['tipo'], item['concepto']): item['monto'] for item in data['gastos_detalle']}
    assert detalle == {('caja', 'Garrafa de gas'): 5000, ('fijo', 'Luz Ganancia'): 2000, ('sueldo', 'Sueldos'): 3000}
    assert totales['unidades_sin_costo'] == 1
    assert len(data['dias']) == 1
    assert [item['nombre'] for item in data['platos_sin_costo']] == ['Bebida']
    pizza = next(item for item in data['platos'] if item['producto_id'] == pizza_id)
    assert pizza['ganancia'] == 56000


def test_precios_insumos_lista_solo_los_usados_en_recetas():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, pizza_id, _bebida_id = _crear_productos(app, 'Resto Precios', 'resto_precios')
    insumo_id = _crear_insumo_receta(app, cliente_id, pizza_id, nombre='Harina Precios', stock=10, cantidad=200)
    _loguear(client, app, 'resto_precios')

    resp = client.get('/api/gastronomia/stock/insumos/precios')
    assert resp.status_code == 200
    insumos = resp.get_json()['insumos']
    assert [(item['id_producto'], item['platos'], item['precio_compra']) for item in insumos] == [(insumo_id, 1, 0.0)]


def test_egreso_marcado_como_compra_insumos_guarda_referencia():
    app = create_app('testing')
    client = app.test_client()
    _crear_productos(app, 'Resto Insumos', 'resto_insumos')
    _loguear(client, app, 'resto_insumos')
    _abrir_caja(app, 'resto_insumos')
    html = client.get('/caja/movimiento').get_data(as_text=True)
    assert 'es_compra_insumos' in html
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))

    for motivo, extra in (('Carne', {'es_compra_insumos': '1'}), ('Taxi', {}), ('Aporte', {'es_compra_insumos': '1'})):
        tipo = 'ingreso' if motivo == 'Aporte' else 'egreso'
        resp = client.post('/caja/movimiento', data={'csrf_token': csrf, 'tipo': tipo, 'monto': 1000, 'motivo': motivo, **extra})
        assert resp.status_code in (200, 302)

    with app.app_context():
        refs = {mov.motivo: mov.referencia_tipo for mov in MovimientoCaja.query.filter(MovimientoCaja.motivo.in_(['Carne', 'Taxi', 'Aporte']))}
    # Solo un egreso puede ser compra de insumos; un ingreso nunca.
    assert refs == {'Carne': REFERENCIA_COMPRA_INSUMOS, 'Taxi': None, 'Aporte': None}
