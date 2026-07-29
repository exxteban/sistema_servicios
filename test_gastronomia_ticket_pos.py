from app import create_app, db
from gastronomia.models import GastronomiaGrupoOpciones, GastronomiaOpcionProducto, GastronomiaPedidoPago
from gastronomia.services.ticket_modifier_service import format_ticket_modifier
from test_gastronomia_caja import _abrir_caja, _crear_pedido_abierto, _crear_producto, _csrf, _loguear


def test_ticket_final_y_cancelacion_regresan_al_pos():
    app = create_app('testing')
    client = app.test_client()
    _cliente_id, producto_id = _crear_producto(app, 'Resto Ticket POS', 'resto_ticket_pos')
    _loguear(client, app, 'resto_ticket_pos')
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    pedido_id = _crear_pedido_abierto(client, csrf, producto_id)

    preview_html = client.get(
        f'/gastronomia/pedidos/{pedido_id}/ticket?preview=1',
    ).get_data(as_text=True)
    assert 'Cancelar y volver al POS' in preview_html
    assert 'href="/gastronomia/pos"' in preview_html

    ticket_html = client.get(f'/gastronomia/pedidos/{pedido_id}/ticket').get_data(as_text=True)
    assert 'window.onafterprint = volverAlPos;' in ticket_html
    assert 'window.opener.location.href = posUrl;' in ticket_html
    assert 'window.location.href = posUrl;' in ticket_html


def test_tickets_gastronomia_y_venta_muestran_modificadores_con_precio():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Ticket Modificadores', 'resto_ticket_modificadores')
    with app.app_context():
        extras = GastronomiaGrupoOpciones(
            cliente_id=cliente_id,
            producto_id=producto_id,
            nombre='Adicionales',
            tipo='extra',
            max_selecciones=2,
        )
        removibles = GastronomiaGrupoOpciones(
            cliente_id=cliente_id,
            producto_id=producto_id,
            nombre='Ingredientes removibles',
            tipo='ingrediente_removible',
            max_selecciones=1,
        )
        db.session.add_all([extras, removibles])
        db.session.flush()
        extra_carne = GastronomiaOpcionProducto(
            cliente_id=cliente_id,
            grupo_id=extras.id_grupo,
            nombre='Extra carne',
            precio_delta=6000,
        )
        sin_carne = GastronomiaOpcionProducto(
            cliente_id=cliente_id,
            grupo_id=removibles.id_grupo,
            nombre='Carne',
            precio_delta=-8000,
        )
        db.session.add_all([extra_carne, sin_carne])
        db.session.commit()
        option_ids = [extra_carne.id_opcion, sin_carne.id_opcion]

    _loguear(client, app, 'resto_ticket_modificadores')
    _abrir_caja(app, 'resto_ticket_modificadores')
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mostrador',
            'items': [{'producto_id': producto_id, 'cantidad': 1, 'opciones': option_ids}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido_resp.status_code == 201
    pedido_id = pedido_resp.get_json()['pedido']['id_pedido']

    gastro_ticket = client.get(
        f'/gastronomia/pedidos/{pedido_id}/ticket?preview=1',
    ).get_data(as_text=True)
    assert 'Extra carne +Gs. 6.000' in gastro_ticket
    assert 'Sin Carne -Gs. 8.000' in gastro_ticket

    cobrar_resp = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf},
    )
    assert cobrar_resp.status_code == 200
    with app.app_context():
        venta_id = GastronomiaPedidoPago.query.filter_by(pedido_id=pedido_id).one().id_venta
    venta_ticket = client.get(f'/ventas/{venta_id}/ticket?preview=1').get_data(as_text=True)
    assert 'Extra carne +Gs. 6.000' in venta_ticket
    assert 'Sin Carne -Gs. 8.000' in venta_ticket


def test_formato_ticket_omite_precio_cero():
    modifier = type('Modifier', (), {
        'nombre_opcion': 'Sin cebolla',
        'tipo_grupo': 'ingrediente_removible',
        'precio_delta': 0,
    })()
    assert format_ticket_modifier(modifier) == 'Sin cebolla'
