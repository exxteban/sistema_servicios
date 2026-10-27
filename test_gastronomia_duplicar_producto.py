from app import create_app
from test_gastronomia_pedidos import _agregar_insumo, _crear_menu_para_pedidos, _csrf, _loguear


def _receta(client, producto_id):
    receta = client.get(f'/api/gastronomia/stock/productos/{producto_id}/receta').get_json()['receta']
    items = sorted((item['insumo_nombre'], item['cantidad']) for item in receta['items'])
    producto = client.get(f'/api/gastronomia/productos/{producto_id}?modificadores=1').get_json()['producto']
    nombres_opcion = {
        opcion['id_opcion']: (grupo['nombre'], opcion['nombre'])
        for grupo in producto['grupos_opciones']
        for opcion in grupo['opciones']
    }
    opciones = sorted(
        (*nombres_opcion[item['opcion_id']], item['insumo_nombre'], item['cantidad_delta'])
        for item in receta['opciones']
    )
    return items, opciones


def test_duplicar_producto_copia_receta_grupos_e_insumos_de_extras():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id, opcion_queso_id = _crear_menu_para_pedidos(app, 'Resto Clon', 'resto_clon')
    medallon = _agregar_insumo(app, cliente_id, 'Tapa de costilla', 5000, unidad='g')
    cheddar = _agregar_insumo(app, cliente_id, 'Cheddar feta', 100)
    cebolla = _agregar_insumo(app, cliente_id, 'Cebolla', 3000, unidad='g')
    _loguear(client, app, 'resto_clon')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))
    headers = {'X-CSRFToken': csrf}

    original = client.get(f'/api/gastronomia/productos/{producto_id}').get_json()['producto']
    base = {
        'categoria_id': str(original['categoria_id']),
        'precio': '28000',
        'ingredientes_removibles': 'cebolla',
        'adicionales_precio': 'carne extra | 8000',
    }
    assert client.put(f'/api/gastronomia/productos/{producto_id}', data={**base, 'nombre': 'La Gus simple'}, headers=headers).status_code == 200
    grupos = client.get(f'/api/gastronomia/productos/{producto_id}?modificadores=1').get_json()['producto']['grupos_opciones']
    opcion_id = {opcion['nombre'].lower(): opcion['id_opcion'] for grupo in grupos for opcion in grupo['opciones']}
    assert client.put(
        f'/api/gastronomia/stock/productos/{producto_id}/receta',
        json={
            'items': [{'insumo_id': medallon, 'cantidad': 120}, {'insumo_id': cheddar, 'cantidad': 1}],
            'opciones': [
                {'opcion_id': opcion_id['carne extra'], 'insumo_id': medallon, 'cantidad_delta': 120},
                {'opcion_id': opcion_id['cebolla'], 'insumo_id': cebolla, 'cantidad_delta': -20},
                {'opcion_id': opcion_queso_id, 'insumo_id': cheddar, 'cantidad_delta': 1},
            ],
        },
        headers=headers,
    ).status_code == 200
    esperado = _receta(client, producto_id)

    copia_resp = client.post(
        '/api/gastronomia/productos',
        data={**base, 'nombre': 'La Gus doble', 'clonar_desde': str(producto_id)},
        headers=headers,
    )
    assert copia_resp.status_code == 201
    copia_id = copia_resp.get_json()['producto']['id_producto']

    assert _receta(client, copia_id) == esperado
    assert _receta(client, producto_id) == esperado
    assert ('Extras', 'Queso', 'Cheddar feta', 1) in esperado[1]
    assert any(nombre_opcion.lower() == 'cebolla' for _grupo, nombre_opcion, _insumo, _delta in esperado[1])

    # Si al duplicar se borraron los ingredientes removibles, no se recrean desde el original.
    sin_removibles = client.post(
        '/api/gastronomia/productos',
        data={**base, 'nombre': 'La Gus triple', 'ingredientes_removibles': '', 'clonar_desde': str(producto_id)},
        headers=headers,
    ).get_json()['producto']
    items, opciones = _receta(client, sin_removibles['id_producto'])
    assert items == esperado[0]
    assert all(nombre_opcion.lower() != 'cebolla' for _grupo, nombre_opcion, _insumo, _delta in opciones)
    assert ('Extras', 'Queso', 'Cheddar feta', 1) in opciones
