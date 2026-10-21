"""Ingreso manual de caja: avisa que no es una venta, y un pedido no se marca cobrado sin cobro."""
import re

from app import create_app
from app.models import MovimientoCaja, Venta
from test_gastronomia_caja import _abrir_caja, _crear_pedido_listo, _crear_producto, _csrf, _loguear


def test_formulario_ingreso_manual_avisa_que_no_es_venta():
    app = create_app('testing')
    client = app.test_client()
    _crear_producto(app, 'Resto Mov', 'resto_mov')
    _loguear(client, app, 'resto_mov')
    _abrir_caja(app, 'resto_mov')

    page = client.get('/caja/movimiento')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Esto no registra una venta' in html
    assert 'Ir al POS' in html or 'Ir a Nueva Venta' in html
    assert 'El motivo parece una venta' in html

    # El aviso no bloquea: el ingreso se sigue guardando.
    resp = client.post('/caja/movimiento', data={
        'csrf_token': re.search(r'name="csrf_token" value="([^"]+)"', html).group(1),
        'tipo': 'ingreso',
        'monto': '50000',
        'motivo': 'Aporte de cambio',
    })
    assert resp.status_code == 302
    assert resp.headers['Location'].rstrip('/').endswith('/caja')
    with app.app_context():
        assert MovimientoCaja.query.filter_by(motivo='Aporte de cambio').count() == 1


def test_pedido_no_se_marca_cobrado_sin_cobro():
    app = create_app('testing')
    client = app.test_client()
    _, producto_id = _crear_producto(app, 'Resto Estado', 'resto_estado')
    _loguear(client, app, 'resto_estado')
    _abrir_caja(app, 'resto_estado')
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)

    resp = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/estado',
        json={'estado': 'cobrado'},
        headers={'X-CSRFToken': csrf},
    )
    assert resp.status_code == 400
    assert 'cobralo desde la caja' in resp.get_json().get('mensaje', '')
    with app.app_context():
        assert Venta.query.count() == 0
