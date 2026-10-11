"""Factura electronica en el POS central (incluye el cobro avanzado de gastronomia)."""
import re

import pytest

from app import create_app, db
from app.models import Cliente
from app.routes.ventas import factura_electronica_pos as fe_pos_routes
from app.routes.ventas import parte2 as pos_routes
from test_gastronomia_caja import _abrir_caja, _crear_producto, _loguear


def _fe_lista(lista=True, activo=True):
    return {'activo': activo, 'lista': lista, 'timeout_ms': 110000, 'tope_innominado': 7_000_000}


def _csrf(html):
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert match is not None
    return match.group(1)


@pytest.fixture
def entorno(monkeypatch):
    app = create_app('testing')
    client = app.test_client()
    _crear_producto(app, 'POS FE', 'pos_fe')
    _loguear(client, app, 'pos_fe')
    _abrir_caja(app, 'pos_fe')
    monkeypatch.setattr(pos_routes, 'contexto_factura_electronica_pos', lambda: _fe_lista(True))
    monkeypatch.setattr(fe_pos_routes, 'contexto_factura_electronica_pos', lambda: _fe_lista(True))
    html = client.get('/ventas/pos').get_data(as_text=True)
    return app, client, _csrf(html)


def _validar(client, csrf, **data):
    return client.post('/ventas/pos/factura-electronica/validar', json=data, headers={'X-CSRFToken': csrf})


def test_pos_muestra_checkbox_solo_con_fe_lista(entorno, monkeypatch):
    _app, client, _csrf_token = entorno
    assert 'Emitir factura electronica' in client.get('/ventas/pos').get_data(as_text=True)

    monkeypatch.setattr(pos_routes, 'contexto_factura_electronica_pos', lambda: _fe_lista(False))
    html = client.get('/ventas/pos').get_data(as_text=True)
    assert 'Emitir factura electronica' not in html
    assert 'configuracion incompleta' in html

    monkeypatch.setattr(pos_routes, 'contexto_factura_electronica_pos', lambda: _fe_lista(False, activo=False))
    html = client.get('/ventas/pos').get_data(as_text=True)
    assert 'Emitir factura electronica' not in html and 'configuracion incompleta' not in html


def test_validar_consumidor_final_bajo_el_tope_es_ok(entorno):
    _app, client, csrf = entorno
    resp = _validar(client, csrf, id_cliente=1, total=50_000)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['ok'] is True


def test_validar_consumidor_final_sobre_el_tope_se_rechaza(entorno, monkeypatch):
    _app, client, csrf = entorno
    from facturacion_electronica.services import validacion
    monkeypatch.setattr(validacion, 'TOPE_INNOMINADO', 20_000)
    resp = _validar(client, csrf, id_cliente=1, total=30_000)
    assert resp.status_code == 400
    assert 'RUC o cedula' in resp.get_json()['mensaje']


def test_validar_empresa_sin_dv_se_rechaza(entorno):
    app, client, csrf = entorno
    with app.app_context():
        receptor = Cliente(nombre='Comercial SRL', ruc_ci='80012345', tipo='minorista', activo=True)
        db.session.add(receptor)
        db.session.commit()
        receptor_id = receptor.id_cliente
    resp = _validar(client, csrf, id_cliente=receptor_id, total=30_000)
    assert resp.status_code == 400
    assert 'dígito verificador' in resp.get_json()['mensaje']


def test_validar_con_modulo_no_listo_se_rechaza(entorno, monkeypatch):
    _app, client, csrf = entorno
    monkeypatch.setattr(fe_pos_routes, 'contexto_factura_electronica_pos', lambda: _fe_lista(False))
    resp = _validar(client, csrf, id_cliente=1, total=10_000)
    assert resp.status_code == 400
