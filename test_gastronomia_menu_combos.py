from app import db
from app.models.producto import Producto
from app.models.tienda_promocion import TiendaPromocion
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaGrupoOpciones,
    GastronomiaProducto,
)
from test_gastronomia_menu_plantillas import _preparar
from test_gastronomia_modificadores import _crear_producto_base
from test_gastronomia_pedidos import _agregar_insumo


def _producto(app, cliente_id, categoria_nombre, nombre, precio, *, control_stock=False):
    with app.app_context():
        categoria = GastronomiaCategoria.query.filter_by(cliente_id=cliente_id, nombre=categoria_nombre).first()
        if categoria is None:
            categoria = GastronomiaCategoria(cliente_id=cliente_id, nombre=categoria_nombre)
            db.session.add(categoria)
            db.session.flush()
        producto = GastronomiaProducto(
            cliente_id=cliente_id,
            categoria_id=categoria.id_categoria,
            nombre=nombre,
            precio=precio,
            control_stock_venta=control_stock,
            stock_disponible=10 if control_stock else None,
        )
        db.session.add(producto)
        db.session.commit()
        return producto.id_producto


def _receta(client, csrf, producto_id, insumo_id, cantidad):
    response = client.put(
        f'/api/gastronomia/stock/productos/{producto_id}/receta',
        json={'items': [{'insumo_id': insumo_id, 'cantidad': cantidad}]},
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 200, response.get_json()


def _crear_combo(client, csrf, payload):
    return client.post('/api/gastronomia/combos', json=payload, headers={'X-CSRFToken': csrf})


def test_menu_muestra_boton_hacer_promo_y_modal():
    _app, _client, _cliente_id, producto_id, _csrf, html = _preparar('Resto Promo Vista', 'resto_promo_vista')

    assert f'data-promo-producto="{producto_id}"' in html
    assert 'id="gastro-promo-modal"' in html
    assert 'id="gastro-promo-productos-data"' in html
    assert 'data-promo-paso="combo"' in html


def test_combo_crea_producto_con_bebida_a_eleccion_y_receta_sumada():
    app, client, cliente_id, pizza_id, csrf, _html = _preparar('Resto Combo', 'resto_combo')
    papas_id = _producto(app, cliente_id, 'Acompanamientos', 'Papas fritas', 12000)
    gaseosa_id = _producto(app, cliente_id, 'Bebidas', 'Gaseosa 500 ml', 8000)
    agua_id = _producto(app, cliente_id, 'Bebidas', 'Agua mineral', 6000)
    masa_id = _agregar_insumo(app, cliente_id, 'Masa combo', 10)
    papa_id = _agregar_insumo(app, cliente_id, 'Papa combo', 10)
    lata_id = _agregar_insumo(app, cliente_id, 'Lata combo', 10)
    _receta(client, csrf, pizza_id, masa_id, 1)
    _receta(client, csrf, papas_id, papa_id, 2)
    _receta(client, csrf, gaseosa_id, lata_id, 1)

    response = _crear_combo(client, csrf, {
        'nombre': 'Combo pizza + papas + bebida',
        'precio': '42.000',
        'producto_ids': [pizza_id, papas_id],
        'bebida_ids': [gaseosa_id, agua_id],
    })

    assert response.status_code == 201, response.get_json()
    data = response.get_json()
    combo_id = data['producto']['id_producto']
    assert data['avisos'] == []
    with app.app_context():
        combo = db.session.get(GastronomiaProducto, combo_id)
        assert combo.categoria.nombre == 'Combos'
        assert int(combo.precio) == 42000
        assert combo.descripcion == 'Incluye: Pizza muzzarella, Papas fritas, bebida a eleccion.'
        grupo = GastronomiaGrupoOpciones.query.filter_by(producto_id=combo_id).one()
        assert (grupo.tipo, grupo.obligatorio, grupo.min_selecciones, grupo.max_selecciones) == ('combo', True, 1, 1)
        opciones = {opcion.nombre: opcion.id_opcion for opcion in grupo.opciones_ordenadas()}
        assert set(opciones) == {'Gaseosa 500 ml', 'Agua mineral'}

    pedido = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mostrador',
            'items': [{'producto_id': combo_id, 'cantidad': 1, 'opciones': [opciones['Gaseosa 500 ml']]}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido.status_code == 201, pedido.get_json()
    assert float(pedido.get_json()['pedido']['total']) == 42000
    with app.app_context():
        assert db.session.get(Producto, masa_id).stock_actual == 9
        assert db.session.get(Producto, papa_id).stock_actual == 8
        assert db.session.get(Producto, lata_id).stock_actual == 9


def test_combo_valida_minimos_precio_y_productos_de_otro_cliente():
    app, client, cliente_id, pizza_id, csrf, _html = _preparar('Resto Combo Valida', 'resto_combo_valida')
    _otro_cliente, otro_producto_id = _crear_producto_base(app, 'Resto Ajeno', 'resto_ajeno')
    papas_id = _producto(app, cliente_id, 'Acompanamientos', 'Papas fritas', 12000, control_stock=True)

    solo_uno = _crear_combo(client, csrf, {'nombre': 'Combo', 'precio': '30000', 'producto_ids': [pizza_id]})
    assert solo_uno.status_code == 400
    assert 'al menos dos' in solo_uno.get_json()['mensaje']

    sin_precio = _crear_combo(client, csrf, {'nombre': 'Combo', 'precio': '', 'producto_ids': [pizza_id, papas_id]})
    assert sin_precio.status_code == 400

    ajeno = _crear_combo(client, csrf, {'nombre': 'Combo', 'precio': '30000', 'producto_ids': [pizza_id, otro_producto_id]})
    assert ajeno.status_code == 400

    doble = _crear_combo(client, csrf, {'nombre': 'Dos pizzas', 'precio': '50000', 'producto_ids': [pizza_id, pizza_id, papas_id]})
    assert doble.status_code == 201, doble.get_json()
    assert doble.get_json()['avisos'] and 'Papas fritas' in doble.get_json()['avisos'][0]
    with app.app_context():
        combo = db.session.get(GastronomiaProducto, doble.get_json()['producto']['id_producto'])
        assert combo.descripcion == 'Incluye: 2 x Pizza muzzarella, Papas fritas.'


def test_promo_rapida_usa_api_de_promociones_con_cliente_gastronomia():
    app, client, cliente_id, pizza_id, csrf, _html = _preparar('Resto Promo Rapida', 'resto_promo_rapida')

    response = client.post(
        '/api/tienda/admin/promociones',
        json={
            'nombre': '2x1 en Pizza muzzarella',
            'tipo': 'cantidad',
            'valor': 1,
            'cantidad_lleva': 2,
            'cantidad_paga': 1,
            'fecha_inicio': '2026-10-19T10:00',
            'fecha_fin': '2026-11-18T10:00',
            'activa': True,
            'productos': [],
            'productos_gastronomia': [pizza_id],
            'cliente_id_gastronomia': str(cliente_id),
        },
        headers={'X-CSRFToken': csrf},
    )

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        promo = TiendaPromocion.query.filter_by(id_cliente=cliente_id).one()
        assert promo.activa is True
        assert [rel.id_producto for rel in promo.gastronomia_productos_rel] == [pizza_id]
