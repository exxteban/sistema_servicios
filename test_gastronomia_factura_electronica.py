"""Factura electronica en la caja gastronomica (porte del modulo del sistema padre)."""
from decimal import Decimal

import pytest

from app import create_app, db
from app.models import Cliente, Configuracion, DetalleVenta, Venta
from app.models.servicio import Servicio
from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO, ESTADO_APROBADO, TIPO_FACTURA
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.data_builder import construir_item
from gastronomia.models import GastronomiaPedido
from gastronomia.services import caja_service
from gastronomia.routes import caja_routes
from gastronomia.services.anulacion_service import anular_venta_gastronomica
from test_gastronomia_caja import _abrir_caja, _crear_pedido_listo, _crear_producto, _csrf, _loguear


def _fe_lista(lista=True):
    return {'activo': True, 'lista': lista, 'timeout_ms': 110000, 'tope_innominado': 7_000_000}


@pytest.fixture
def entorno(monkeypatch):
    app = create_app('testing')
    client = app.test_client()
    tenant_id, producto_id = _crear_producto(app, 'Resto FE', 'resto_fe')
    _loguear(client, app, 'resto_fe')
    _abrir_caja(app, 'resto_fe')
    monkeypatch.setattr(caja_service, 'contexto_factura_electronica_caja', lambda: _fe_lista(True))
    monkeypatch.setattr(caja_routes, 'contexto_factura_electronica_caja', lambda: _fe_lista(True))
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    return app, client, csrf, producto_id


def _cobrar(client, csrf, pedido_id, **extra):
    return client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo', **extra},
        headers={'X-CSRFToken': csrf},
    )


def test_caja_muestra_panel_solo_con_fe_lista(entorno, monkeypatch):
    _app, client, _csrf_token, _producto_id = entorno
    assert 'id="fe-panel"' in client.get('/gastronomia/caja').get_data(as_text=True)

    monkeypatch.setattr(caja_routes, 'contexto_factura_electronica_caja', lambda: _fe_lista(False))
    html = client.get('/gastronomia/caja').get_data(as_text=True)
    assert 'id="fe-panel"' not in html
    assert 'configuracion incompleta' in html

    monkeypatch.setattr(caja_routes, 'contexto_factura_electronica_caja', lambda: {**_fe_lista(False), 'activo': False})
    html = client.get('/gastronomia/caja').get_data(as_text=True)
    assert 'id="fe-panel"' not in html and 'configuracion incompleta' not in html


def test_contexto_real_sin_modulo_activo_no_ofrece_factura():
    app = create_app('testing')
    with app.app_context():
        Configuracion.establecer_bool(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, False)
        from gastronomia.services.factura_electronica_service import contexto_factura_electronica_caja
        contexto = contexto_factura_electronica_caja()
        assert contexto['activo'] is False
        assert contexto['lista'] is False


def test_cobro_con_factura_queda_a_nombre_del_cliente_elegido(entorno):
    app, client, csrf, producto_id = entorno
    with app.app_context():
        receptor = Cliente(nombre='Empresa SA', ruc_ci='80012345-6', tipo='minorista', activo=True)
        db.session.add(receptor)
        db.session.commit()
        receptor_id = receptor.id_cliente
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)

    resp = _cobrar(client, csrf, pedido_id, factura_electronica=True, id_cliente_factura=receptor_id)

    assert resp.status_code == 200, resp.get_json()
    id_venta = resp.get_json()['pedido']['pago']['id_venta']
    with app.app_context():
        assert db.session.get(Venta, id_venta).id_cliente == receptor_id


def test_cobro_sin_factura_sigue_a_consumidor_final(entorno):
    app, client, csrf, producto_id = entorno
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)
    resp = _cobrar(client, csrf, pedido_id)
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Venta, resp.get_json()['pedido']['pago']['id_venta']).id_cliente == 1


def test_empresa_sin_dv_frena_el_cobro_antes_de_crear_la_venta(entorno):
    app, client, csrf, producto_id = entorno
    with app.app_context():
        receptor = Cliente(nombre='Comercial SRL', ruc_ci='80012345', tipo='minorista', activo=True)
        db.session.add(receptor)
        db.session.commit()
        receptor_id = receptor.id_cliente
        ventas_antes = Venta.query.count()
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)

    resp = _cobrar(client, csrf, pedido_id, factura_electronica=True, id_cliente_factura=receptor_id)

    assert resp.status_code == 400
    assert 'dígito verificador' in resp.get_json()['mensaje']
    with app.app_context():
        assert Venta.query.count() == ventas_antes
        assert db.session.get(GastronomiaPedido, pedido_id).pago is None


def test_consumidor_final_sobre_el_tope_no_se_puede_facturar(entorno, monkeypatch):
    app, client, csrf, producto_id = entorno
    from facturacion_electronica.services import validacion
    monkeypatch.setattr(validacion, 'TOPE_INNOMINADO', 20_000)
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)  # 30.000 Gs

    resp = _cobrar(client, csrf, pedido_id, factura_electronica=True)

    assert resp.status_code == 400
    assert 'RUC o cedula' in resp.get_json()['mensaje']


def test_factura_pedida_con_modulo_no_listo_se_rechaza(entorno, monkeypatch):
    _app, client, csrf, producto_id = entorno
    monkeypatch.setattr(caja_service, 'contexto_factura_electronica_caja', lambda: _fe_lista(False))
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)
    resp = _cobrar(client, csrf, pedido_id, factura_electronica=True)
    assert resp.status_code == 400


def test_buscar_y_crear_cliente_factura_reusa_el_ruc(entorno):
    app, client, csrf, _producto_id = entorno
    crear = client.post(
        '/api/gastronomia/caja/clientes-factura',
        json={'nombre': 'Juan Perez', 'ruc_ci': '4567890'},
        headers={'X-CSRFToken': csrf},
    )
    assert crear.status_code == 200
    creado = crear.get_json()['cliente']
    otra_vez = client.post(
        '/api/gastronomia/caja/clientes-factura',
        json={'nombre': 'Otro nombre', 'ruc_ci': '4567890'},
        headers={'X-CSRFToken': csrf},
    )
    assert otra_vez.get_json()['cliente']['id_cliente'] == creado['id_cliente']

    encontrados = client.get('/api/gastronomia/caja/clientes-factura?q=4567').get_json()['clientes']
    assert [c['id_cliente'] for c in encontrados] == [creado['id_cliente']]

    sin_ruc = client.post(
        '/api/gastronomia/caja/clientes-factura',
        json={'nombre': 'Sin ruc'},
        headers={'X-CSRFToken': csrf},
    )
    assert sin_ruc.status_code == 400


def test_no_se_anula_venta_gastronomica_con_factura_aprobada(entorno):
    app, client, csrf, producto_id = entorno
    pedido_id = _crear_pedido_listo(client, csrf, producto_id)
    resp = _cobrar(client, csrf, pedido_id)
    id_venta = resp.get_json()['pedido']['pago']['id_venta']
    with app.app_context():
        pedido = db.session.get(GastronomiaPedido, pedido_id)
        db.session.add(DocumentoElectronico(
            id_venta=id_venta, tipo_documento=TIPO_FACTURA, estado=ESTADO_APROBADO,
            cdc='0' * 44,
        ))
        db.session.commit()
        usuario_id = pedido.usuario_id

        with pytest.raises(ValueError, match='factura electrónica vigente'):
            anular_venta_gastronomica(pedido.cliente_id, pedido_id, usuario_id, motivo='prueba')
        assert db.session.get(Venta, id_venta).estado != 'anulada'


def test_item_de_servicio_toma_codigo_y_nombre_del_servicio():
    detalle = DetalleVenta(
        id_producto=None, id_servicio=7, cantidad=2, precio_unitario=15000, precio_original=15000,
        porcentaje_iva=10, monto_iva=0, descuento_linea=0, subtotal=30000,
    )
    detalle.servicio = Servicio(id_servicio=7, codigo=None, nombre='Hamburguesa doble', precio=Decimal('15000'))

    item = construir_item(detalle)

    assert item['codigo'] == 'SRV-7'
    assert item['descripcion'] == 'Hamburguesa doble'
    assert item['iva'] == 10
