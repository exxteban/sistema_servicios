"""Fase 2 del plan de pasteleria: pantallas y endpoints de la venta por peso."""
import re
from datetime import timedelta

from app import create_app, db
from app.models import Rol, Usuario
from app.utils.helpers import now_local
from gastronomia.models import GastronomiaClienteConfig, GastronomiaProducto
from gastronomia.services.adelanto_service import registrar_adelanto
from gastronomia.services.encargo_service import crear_encargo
from test_gastronomia_caja import _abrir_caja, _loguear
from test_gastronomia_pedidos import _crear_menu_para_pedidos


def _local(app, nombre, username, *, peso=True):
    cliente_id, producto_id, _ = _crear_menu_para_pedidos(app, nombre, username)
    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one()
        config.venta_por_peso_activa = peso
        config.encargos_activo = True
        base = db.session.get(GastronomiaProducto, producto_id)
        torta = GastronomiaProducto(
            cliente_id=cliente_id, categoria_id=base.categoria_id, nombre='Torta chocolate', precio=80000, unidad_venta='kg',
        )
        db.session.add(torta)
        db.session.commit()
        return cliente_id, producto_id, torta.id_producto


def _http(app, username):
    client = app.test_client()
    _loguear(client, app, username)
    html = client.get('/gastronomia/pos').get_data(as_text=True)
    return client, re.search(r'id="csrf-token" value="([^"]+)"', html).group(1), html


def test_root_activa_venta_por_peso_y_valida_atajos():
    app = create_app('testing')
    cliente_id, _, _ = _local(app, 'Peso UI 1', 'peso_ui_1', peso=False)
    root = app.test_client()
    _loguear(root, app, 'root')
    html = root.get('/usuarios/modulos-sistema').get_data(as_text=True)
    assert f'data-pasteleria-peso="{cliente_id}"' in html
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    url = f'/usuarios/modulos-sistema/pasteleria/{cliente_id}/peso'
    root.post(url, data={'csrf_token': csrf, 'venta_por_peso_activa': '1', 'peso_atajos_kg': '0.5, 1,1.5'})
    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one()
        assert (config.venta_por_peso_activa, config.peso_atajos_kg) == (True, '0.5,1,1.5')

    resp = root.post(url, data={'csrf_token': csrf, 'peso_atajos_kg': '1,abc'}, follow_redirects=True)
    assert 'Atajos de peso' in resp.get_data(as_text=True)
    with app.app_context():
        assert GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one().venta_por_peso_activa is True


def test_pos_muestra_el_bloque_de_peso_y_el_menu_el_selector_solo_con_flag():
    app = create_app('testing')
    _local(app, 'Peso UI 2', 'peso_ui_2')
    client, _, pos_html = _http(app, 'peso_ui_2')
    assert 'id="modal-peso"' in pos_html
    assert 'data-atajos="1.0,1.5,2.0"' in pos_html
    assert 'js/pos_peso.js' in pos_html
    assert 'name="unidad_venta"' in client.get('/gastronomia/menu').get_data(as_text=True)

    app2 = create_app('testing')
    _local(app2, 'Peso UI 3', 'peso_ui_3', peso=False)
    client2, _, _ = _http(app2, 'peso_ui_3')
    assert 'name="unidad_venta"' not in client2.get('/gastronomia/menu').get_data(as_text=True)


def test_api_de_productos_y_tienda_exponen_unidad_de_venta(monkeypatch):
    app = create_app('testing')
    _, _, torta_id = _local(app, 'Peso UI 4', 'peso_ui_4')
    client, _, _ = _http(app, 'peso_ui_4')
    producto = client.get(f'/api/gastronomia/productos/{torta_id}').get_json()['producto']
    assert producto['unidad_venta'] == 'kg'
    with app.app_context():
        import app.services.tienda_gastronomia_catalogo as catalogo
        from app.services.tienda_gastronomia_catalogo import _serializar_producto_card

        monkeypatch.setattr(catalogo, '_build_whatsapp_link', lambda producto, config: None)
        torta = db.session.get(GastronomiaProducto, torta_id)
        with app.test_request_context():
            data = _serializar_producto_card(torta, type('C', (), {'slug': 'demo'})())
        assert data['unidad_venta'] == 'kg'
        assert data['promocion_activa'] is None


def test_endpoint_ajustar_peso_y_permiso_de_caja_para_devolver():
    app = create_app('testing')
    cliente_id, _, torta_id = _local(app, 'Peso UI 5', 'peso_ui_5')
    _abrir_caja(app, 'peso_ui_5')
    with app.app_context():
        usuario_id = Usuario.query.filter_by(username='peso_ui_5').one().id_usuario
        fecha = (now_local().replace(tzinfo=None) + timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0)
        pedido = crear_encargo(cliente_id, usuario_id, {
            'nombre_cliente': 'Ana', 'fecha_programada': fecha,
            'items': [{'producto_id': torta_id, 'cantidad': 1, 'peso_kg': '2'}],
        })
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 150000})
        pedido_id, item_id = pedido.id_pedido, pedido.items.one().id_item
        mozo = Usuario(
            id_cliente=cliente_id, username='peso_ui_5_mozo', nombre_completo='Mozo',
            id_rol=Rol.query.filter_by(nombre='Mozo').one().id_rol, activo=True,
        )
        mozo.set_password('clave123')
        db.session.add(mozo)
        db.session.commit()

    url = f'/api/gastronomia/encargos/{pedido_id}/items/{item_id}/peso'
    mozo_client, mozo_csrf, _ = _http(app, 'peso_ui_5_mozo')
    assert mozo_client.post(url, json={'peso_kg': '1.9'}, headers={'X-CSRFToken': mozo_csrf}).status_code == 200
    assert mozo_client.post(url, json={'peso_kg': '1.5'}, headers={'X-CSRFToken': mozo_csrf}).status_code == 403

    admin, csrf, _ = _http(app, 'peso_ui_5')
    resp = admin.post(url, json={'peso_kg': '1.5'}, headers={'X-CSRFToken': csrf})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data['sena_devuelta'] == 30000
    assert data['pedido']['total'] == 120000
    assert data['pedido']['items'][0]['peso_kg'] == 1.5
    assert admin.post(url, json={'peso_kg': '0'}, headers={'X-CSRFToken': csrf}).status_code == 400


def test_listado_de_pedidos_incluye_peso_del_item():
    app = create_app('testing')
    cliente_id, _, torta_id = _local(app, 'Peso UI 6', 'peso_ui_6')
    client, csrf, _ = _http(app, 'peso_ui_6')
    resp = client.post('/api/gastronomia/pedidos', json={
        'tipo_pedido': 'mostrador', 'items': [{'producto_id': torta_id, 'cantidad': 1, 'peso_kg': '1.35'}],
    }, headers={'X-CSRFToken': csrf})
    assert resp.status_code == 201, resp.get_json()
    item = client.get('/api/gastronomia/pedidos').get_json()['pedidos'][0]['items'][0]
    assert (item['peso_kg'], item['precio_por_kg'], item['subtotal']) == (1.35, 80000, 108000)
