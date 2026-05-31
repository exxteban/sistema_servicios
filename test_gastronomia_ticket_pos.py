from app import create_app
from test_gastronomia_caja import _crear_pedido_abierto, _crear_producto, _csrf, _loguear


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
