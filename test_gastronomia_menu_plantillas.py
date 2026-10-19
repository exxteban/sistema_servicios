from app import create_app, db
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaGrupoOpciones,
    GastronomiaOpcionProducto,
    GastronomiaProducto,
)
from test_gastronomia_modificadores import _crear_producto_base, _csrf, _loguear


def _preparar(nombre_cliente: str, username: str):
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto_base(app, nombre_cliente, username)
    _loguear(client, app, username)
    html = client.get('/gastronomia/menu').get_data(as_text=True)
    return app, client, cliente_id, producto_id, _csrf(html), html


def _aplicar(client, csrf, productos):
    return client.post(
        '/api/gastronomia/menu-plantillas/aplicar',
        json={'productos': productos},
        headers={'X-CSRFToken': csrf},
    )


def test_menu_muestra_plantillas_y_editor_de_extras():
    _app, _client, _cliente_id, _producto_id, _csrf_token, html = _preparar('Resto Plantilla Vista', 'resto_plantilla_vista')

    assert 'data-entry-tab="plantilla"' in html
    assert 'id="gastro-menu-plantillas-data"' in html
    assert 'Hamburgueseria' in html
    assert 'data-extras-editor="removible"' in html
    assert 'data-extras-editor="adicional"' in html


def test_aplicar_plantilla_crea_categorias_productos_y_extras():
    app, client, cliente_id, _producto_id, csrf, _html = _preparar('Resto Plantilla', 'resto_plantilla')

    response = _aplicar(client, csrf, [
        {
            'categoria': 'Hamburguesas',
            'nombre': 'Hamburguesa clasica',
            'precio': '25.000',
            'removibles': 'lechuga\ntomate',
            'adicionales': 'queso extra | 3000',
        },
        {'categoria': 'Bebidas', 'nombre': 'Gaseosa 500 ml', 'precio': '8000'},
        {'categoria': 'Pizzas', 'nombre': 'Pizza muzzarella', 'precio': '30000'},
    ])

    assert response.status_code == 200, response.get_json()
    data = response.get_json()
    assert data['creados'] == ['Hamburguesa clasica', 'Gaseosa 500 ml']
    assert data['omitidos'] == ['Pizza muzzarella']
    assert sorted(data['categorias_creadas']) == ['Bebidas', 'Hamburguesas']

    with app.app_context():
        burger = GastronomiaProducto.query.filter_by(cliente_id=cliente_id, nombre='Hamburguesa clasica').one()
        assert int(burger.precio) == 25000
        assert burger.categoria.nombre == 'Hamburguesas'
        grupos = GastronomiaGrupoOpciones.query.filter_by(cliente_id=cliente_id, producto_id=burger.id_producto).all()
        assert {grupo.tipo for grupo in grupos} == {'ingrediente_removible', 'extra'}
        opciones = {
            opcion.nombre
            for opcion in GastronomiaOpcionProducto.query.filter_by(cliente_id=cliente_id).all()
        }
        assert {'lechuga', 'tomate', 'queso extra'} <= opciones
        assert GastronomiaCategoria.query.filter_by(cliente_id=cliente_id, nombre='Pizzas').count() == 1


def test_aplicar_plantilla_exige_precio_y_no_crea_nada_si_falta():
    app, client, cliente_id, _producto_id, csrf, _html = _preparar('Resto Plantilla Precio', 'resto_plantilla_precio')

    response = _aplicar(client, csrf, [
        {'categoria': 'Cafes', 'nombre': 'Cafe', 'precio': '7000'},
        {'categoria': 'Cafes', 'nombre': 'Capuchino', 'precio': ''},
    ])

    assert response.status_code == 400
    assert 'Capuchino' in response.get_json()['mensaje']
    with app.app_context():
        assert GastronomiaCategoria.query.filter_by(cliente_id=cliente_id, nombre='Cafes').count() == 0
        assert GastronomiaProducto.query.filter_by(cliente_id=cliente_id, nombre='Cafe').count() == 0


def test_aplicar_plantilla_reactiva_categoria_y_producto_borrados():
    app, client, cliente_id, producto_id, csrf, _html = _preparar('Resto Plantilla Borrados', 'resto_plantilla_borrados')
    with app.app_context():
        producto = db.session.get(GastronomiaProducto, producto_id)
        producto.activo = False
        producto.categoria.activo = False
        db.session.commit()

    response = _aplicar(client, csrf, [{'categoria': 'Pizzas', 'nombre': 'Pizza muzzarella', 'precio': '35000'}])

    assert response.status_code == 200, response.get_json()
    assert response.get_json()['creados'] == ['Pizza muzzarella']
    with app.app_context():
        producto = db.session.get(GastronomiaProducto, producto_id)
        assert producto.activo is True
        assert int(producto.precio) == 35000
        assert producto.categoria.activo is True


def test_aplicar_plantilla_crea_promo_sugerida_pausada():
    from app.models.tienda_promocion import TiendaPromocion

    app, client, cliente_id, _producto_id, csrf, html = _preparar('Resto Plantilla Promo', 'resto_plantilla_promo')
    assert 'data-puede-promos="1"' in html

    response = client.post(
        '/api/gastronomia/menu-plantillas/aplicar',
        json={
            'productos': [{'categoria': 'Hamburguesas', 'nombre': 'Burger de la casa', 'precio': '25000'}],
            'promo': {'plantilla': 'hamburgueseria', 'producto': 'Burger de la casa'},
        },
        headers={'X-CSRFToken': csrf},
    )

    assert response.status_code == 200, response.get_json()
    assert response.get_json()['promo_creada'] == '2x1 en Burger de la casa'
    with app.app_context():
        promo = TiendaPromocion.query.filter_by(id_cliente=cliente_id).one()
        assert promo.activa is False
        assert (promo.tipo, promo.cantidad_lleva, promo.cantidad_paga) == ('cantidad', 2, 1)
        assert [rel.id_producto for rel in promo.gastronomia_productos_rel] == [
            GastronomiaProducto.query.filter_by(cliente_id=cliente_id, nombre='Burger de la casa').one().id_producto
        ]

    repetida = client.post(
        '/api/gastronomia/menu-plantillas/aplicar',
        json={
            'productos': [{'categoria': 'Hamburguesas', 'nombre': 'Burger de la casa', 'precio': '25000'}],
            'promo': {'plantilla': 'hamburgueseria', 'producto': 'Burger de la casa'},
        },
        headers={'X-CSRFToken': csrf},
    )
    assert repetida.get_json()['promo_creada'] is None
    with app.app_context():
        assert TiendaPromocion.query.filter_by(id_cliente=cliente_id).count() == 1


def test_plantilla_sin_promo_no_crea_promocion():
    from app.models.tienda_promocion import TiendaPromocion

    app, client, cliente_id, _producto_id, csrf, _html = _preparar('Resto Plantilla Sin Promo', 'resto_plantilla_sin_promo')

    response = client.post(
        '/api/gastronomia/menu-plantillas/aplicar',
        json={
            'productos': [{'categoria': 'Cafes', 'nombre': 'Cafe', 'precio': '7000'}],
            'promo': {'plantilla': 'cafeteria', 'producto': 'Cafe'},
        },
        headers={'X-CSRFToken': csrf},
    )

    assert response.status_code == 200
    assert response.get_json()['promo_creada'] is None
    with app.app_context():
        assert TiendaPromocion.query.filter_by(id_cliente=cliente_id).count() == 0
