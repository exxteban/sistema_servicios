"""Fase 3 del plan de pasteleria: produccion diaria, porciones y merma."""
import re
from datetime import timedelta

import pytest

from app import create_app, db
from app.models import Producto, Usuario
from gastronomia.models import GastronomiaClienteConfig, GastronomiaProducto
from gastronomia.produccion_models import GastronomiaProduccionRegistro
from gastronomia.services.merma_reporte_service import reporte_merma
from gastronomia.services.pedido_service import cambiar_estado_pedido, crear_pedido
from gastronomia.services.porciones_service import abrir_entero, guardar_relacion
from gastronomia.services.produccion_service import (
    ProduccionDeshabilitadaError,
    cerrar_dia,
    hoy_local,
    registrar_merma,
    registrar_produccion,
    resumen_dia,
)
from gastronomia.services.stock_service import guardar_receta
from test_gastronomia_caja import _loguear
from test_gastronomia_pedidos import _agregar_insumo, _crear_menu_para_pedidos


def _local(app, nombre, username, *, flag=True):
    """Local con medialunas (con control de stock), torta entera y porcion."""
    cliente_id, base_id, _ = _crear_menu_para_pedidos(app, nombre, username)
    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one()
        config.produccion_diaria_activa = flag
        base = db.session.get(GastronomiaProducto, base_id)
        ids = {}
        for clave, nombre_producto in (('medialuna', 'Medialuna'), ('torta', 'Torta entera'), ('porcion', 'Porcion de torta')):
            producto = GastronomiaProducto(
                cliente_id=cliente_id, categoria_id=base.categoria_id, nombre=nombre_producto, precio=5000,
                control_stock_venta=True, stock_disponible=0,
            )
            db.session.add(producto)
            db.session.flush()
            ids[clave] = producto.id_producto
        db.session.commit()
        ids['sin_control'] = base_id
        usuario_id = Usuario.query.filter_by(username=username).first().id_usuario
        return cliente_id, usuario_id, ids


def _stock(producto_id) -> int:
    db.session.expire_all()
    return int(db.session.get(GastronomiaProducto, producto_id).stock_disponible or 0)


def _fila(resumen, producto_id):
    return next(f for f in resumen['productos'] if f['producto_id'] == producto_id)


def test_tanda_venta_y_cierre_con_descarte_dejan_la_merma_del_dia():
    app = create_app('testing')
    cliente_id, usuario_id, ids = _local(app, 'Prod 1', 'prod_1')
    medialuna = ids['medialuna']
    with app.app_context():
        registrar_produccion(cliente_id, usuario_id, {'producto_id': medialuna, 'cantidad': 24})
        assert _stock(medialuna) == 24
        crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'mostrador', 'items': [{'producto_id': medialuna, 'cantidad': 5}],
        })
        assert _stock(medialuna) == 19
        registrar_merma(cliente_id, usuario_id, {'producto_id': medialuna, 'cantidad': 2, 'motivo': 'golpeado'})

        # Quedan 15 contadas (el sistema dice 17): faltan 2. Las 15 se descartan por vencidas.
        cerrar_dia(cliente_id, usuario_id, {'items': [{'producto_id': medialuna, 'quedan': 15, 'destino': 'vencido'}]})
        assert _stock(medialuna) == 0

        fila = _fila(resumen_dia(cliente_id), medialuna)
        assert (fila['producido'], fila['vendido'], fila['merma'], fila['stock']) == (24, 5, 19, 0)
        motivos = {m['motivo']: m['cantidad'] for m in reporte_merma(cliente_id, hoy_local(), hoy_local())['productos'][0]['motivos']}
        assert motivos == {'golpeado': 2, 'faltante': 2, 'vencido': 15}


def test_cierre_con_conteo_mayor_es_ajuste_y_lo_que_sigue_queda_a_la_venta():
    app = create_app('testing')
    cliente_id, usuario_id, ids = _local(app, 'Prod 2', 'prod_2')
    medialuna = ids['medialuna']
    with app.app_context():
        registrar_produccion(cliente_id, usuario_id, {'producto_id': medialuna, 'cantidad': 10})
        cerrar_dia(cliente_id, usuario_id, {'items': [{'producto_id': medialuna, 'quedan': 12, 'destino': 'sigue'}]})
        assert _stock(medialuna) == 12
        fila = _fila(resumen_dia(cliente_id), medialuna)
        assert (fila['ajuste'], fila['merma']) == (2, 0)


def test_venta_cancelada_no_cuenta_como_vendida():
    app = create_app('testing')
    cliente_id, usuario_id, ids = _local(app, 'Prod 3', 'prod_3')
    medialuna = ids['medialuna']
    with app.app_context():
        registrar_produccion(cliente_id, usuario_id, {'producto_id': medialuna, 'cantidad': 6})
        pedido = crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'mostrador', 'items': [{'producto_id': medialuna, 'cantidad': 3}],
        })
        cambiar_estado_pedido(cliente_id, pedido.id_pedido, 'cancelado')
        assert _stock(medialuna) == 6
        assert _fila(resumen_dia(cliente_id), medialuna)['vendido'] == 0


def test_validaciones_de_tanda_merma_y_cierre():
    app = create_app('testing')
    cliente_id, usuario_id, ids = _local(app, 'Prod 4', 'prod_4')
    with app.app_context():
        with pytest.raises(ValueError, match='no controla stock'):
            registrar_produccion(cliente_id, usuario_id, {'producto_id': ids['sin_control'], 'cantidad': 5})
        for cantidad in (0, -3, 'abc', 10001):
            with pytest.raises(ValueError):
                registrar_produccion(cliente_id, usuario_id, {'producto_id': ids['medialuna'], 'cantidad': cantidad})
        registrar_produccion(cliente_id, usuario_id, {'producto_id': ids['medialuna'], 'cantidad': 3})
        with pytest.raises(ValueError, match='Solo hay 3'):
            registrar_merma(cliente_id, usuario_id, {'producto_id': ids['medialuna'], 'cantidad': 4, 'motivo': 'vencido'})
        with pytest.raises(ValueError, match='motivo'):
            registrar_merma(cliente_id, usuario_id, {'producto_id': ids['medialuna'], 'cantidad': 1, 'motivo': 'faltante'})
        with pytest.raises(ValueError, match='repetido'):
            cerrar_dia(cliente_id, usuario_id, {'items': [
                {'producto_id': ids['medialuna'], 'quedan': 1}, {'producto_id': ids['medialuna'], 'quedan': 1},
            ]})
        # Un cierre invalido no mueve nada (se valida todo antes).
        with pytest.raises(ValueError):
            cerrar_dia(cliente_id, usuario_id, {'items': [
                {'producto_id': ids['medialuna'], 'quedan': 0}, {'producto_id': ids['torta'], 'quedan': -1},
            ]})
        assert _stock(ids['medialuna']) == 3


def test_abrir_torta_con_y_sin_stock():
    app = create_app('testing')
    cliente_id, usuario_id, ids = _local(app, 'Prod 5', 'prod_5')
    with app.app_context():
        guardar_relacion(cliente_id, ids['torta'], {'producto_porcion_id': ids['porcion'], 'porciones': 12})
        with pytest.raises(ValueError, match='No hay'):
            abrir_entero(cliente_id, usuario_id, ids['torta'])

        registrar_produccion(cliente_id, usuario_id, {'producto_id': ids['torta'], 'cantidad': 1})
        resultado = abrir_entero(cliente_id, usuario_id, ids['torta'])
        assert (_stock(ids['torta']), _stock(ids['porcion'])) == (0, 12)
        registros = GastronomiaProduccionRegistro.query.filter_by(referencia=resultado['referencia']).all()
        assert sorted(r.tipo for r in registros) == ['apertura', 'porciones']

        # Segunda apertura seguida con el stock ya consumido: se rechaza y no mueve nada.
        with pytest.raises(ValueError, match='No hay'):
            abrir_entero(cliente_id, usuario_id, ids['torta'])
        assert (_stock(ids['torta']), _stock(ids['porcion'])) == (0, 12)


def test_relaciones_de_porciones_invalidas():
    app = create_app('testing')
    cliente_id, _, ids = _local(app, 'Prod 6', 'prod_6')
    with app.app_context():
        with pytest.raises(ValueError, match='distinto'):
            guardar_relacion(cliente_id, ids['torta'], {'producto_porcion_id': ids['torta'], 'porciones': 8})
        with pytest.raises(ValueError, match='no controla stock'):
            guardar_relacion(cliente_id, ids['torta'], {'producto_porcion_id': ids['sin_control'], 'porciones': 8})
        with pytest.raises(ValueError, match='porciones'):
            guardar_relacion(cliente_id, ids['torta'], {'producto_porcion_id': ids['porcion'], 'porciones': 0})
        guardar_relacion(cliente_id, ids['torta'], {'producto_porcion_id': ids['porcion'], 'porciones': 8})
        with pytest.raises(ValueError, match='ya se abre'):
            guardar_relacion(cliente_id, ids['medialuna'], {'producto_porcion_id': ids['torta'], 'porciones': 2})
        with pytest.raises(ValueError, match='ya es porcion'):
            guardar_relacion(cliente_id, ids['porcion'], {'producto_porcion_id': ids['medialuna'], 'porciones': 2})


def test_merma_valorizada_con_costo_congelado():
    app = create_app('testing')
    cliente_id, usuario_id, ids = _local(app, 'Prod 7', 'prod_7')
    insumo_id = _agregar_insumo(app, cliente_id, 'Manteca prod 7', 1000)
    with app.app_context():
        db.session.get(Producto, insumo_id).precio_compra = 100
        db.session.commit()
        guardar_receta(cliente_id, ids['medialuna'], {'items': [{'insumo_id': insumo_id, 'cantidad': 3}]})
        registrar_produccion(cliente_id, usuario_id, {'producto_id': ids['medialuna'], 'cantidad': 10})
        registrar_merma(cliente_id, usuario_id, {'producto_id': ids['medialuna'], 'cantidad': 2, 'motivo': 'vencido'})

        # Cambia el costo despues: el reporte conserva el costo del momento.
        db.session.get(Producto, insumo_id).precio_compra = 999
        db.session.commit()
        reporte = reporte_merma(cliente_id, hoy_local(), hoy_local())
        assert reporte['total_costo'] == 600
        assert reporte['productos'][0]['sin_costo'] is False

        registrar_produccion(cliente_id, usuario_id, {'producto_id': ids['torta'], 'cantidad': 1})
        registrar_merma(cliente_id, usuario_id, {'producto_id': ids['torta'], 'cantidad': 1, 'motivo': 'regalado'})
        torta = next(p for p in reporte_merma(cliente_id, hoy_local(), hoy_local())['productos'] if p['producto_id'] == ids['torta'])
        assert (torta['costo'], torta['sin_costo']) == (0, True)

        with pytest.raises(ValueError):
            reporte_merma(cliente_id, hoy_local(), hoy_local() - timedelta(days=1))


def test_otro_cliente_no_opera_productos_ajenos():
    app = create_app('testing')
    cliente_a, usuario_a, _ = _local(app, 'Prod 8a', 'prod_8a')
    _, _, ids_b = _local(app, 'Prod 8b', 'prod_8b')
    with app.app_context():
        with pytest.raises(ValueError, match='no encontrado'):
            registrar_produccion(cliente_a, usuario_a, {'producto_id': ids_b['medialuna'], 'cantidad': 5})
        assert _stock(ids_b['medialuna']) == 0


def test_flag_apagado_rechaza_servicio_api_pantalla_y_tarjeta():
    app = create_app('testing')
    cliente_id, usuario_id, ids = _local(app, 'Prod 9', 'prod_9', flag=False)
    with app.app_context():
        with pytest.raises(ProduccionDeshabilitadaError):
            registrar_produccion(cliente_id, usuario_id, {'producto_id': ids['medialuna'], 'cantidad': 5})
    client = app.test_client()
    _loguear(client, app, 'prod_9')
    assert client.get('/api/gastronomia/produccion/dia').status_code == 404
    assert client.get('/gastronomia/produccion').status_code == 302
    assert 'gastronomia/produccion' not in client.get('/gastronomia/').get_data(as_text=True)


def test_pantalla_y_api_con_flag():
    app = create_app('testing')
    _, _, ids = _local(app, 'Prod 10', 'prod_10')
    client = app.test_client()
    _loguear(client, app, 'prod_10')
    assert '/gastronomia/produccion' in client.get('/gastronomia/').get_data(as_text=True)
    html = client.get('/gastronomia/produccion').get_data(as_text=True)
    assert 'data-gastro-produccion' in html and 'js/produccion.js' in html
    csrf = re.search(r'id="csrf-token" value="([^"]+)"', html).group(1)
    headers = {'X-CSRFToken': csrf}

    resp = client.post('/api/gastronomia/produccion/tandas', json={'producto_id': ids['torta'], 'cantidad': 2}, headers=headers)
    assert resp.status_code == 201
    resp = client.put(f'/api/gastronomia/produccion/productos/{ids["torta"]}/porciones',
                      json={'producto_porcion_id': ids['porcion'], 'porciones': 10}, headers=headers)
    assert resp.status_code == 200
    resp = client.post(f'/api/gastronomia/produccion/productos/{ids["torta"]}/abrir', headers=headers)
    assert resp.status_code == 200 and resp.get_json()['porcion']['stock'] == 10
    resp = client.post('/api/gastronomia/produccion/mermas',
                       json={'producto_id': ids['porcion'], 'cantidad': 99, 'motivo': 'vencido'}, headers=headers)
    assert resp.status_code == 400

    data = client.get('/api/gastronomia/produccion/dia').get_json()
    torta = next(p for p in data['productos'] if p['producto_id'] == ids['torta'])
    assert torta['stock'] == 1 and torta['relacion_porciones']['porciones'] == 10
    assert client.get('/api/gastronomia/produccion/merma').status_code == 200


def test_root_enciende_produccion_diaria():
    app = create_app('testing')
    cliente_id, _, _ = _local(app, 'Prod 11', 'prod_11', flag=False)
    root = app.test_client()
    _loguear(root, app, 'root')
    html = root.get('/usuarios/modulos-sistema').get_data(as_text=True)
    assert f'data-pasteleria-produccion="{cliente_id}"' in html
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    root.post(f'/usuarios/modulos-sistema/pasteleria/{cliente_id}/produccion',
              data={'csrf_token': csrf, 'produccion_diaria_activa': '1'})
    with app.app_context():
        assert GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one().produccion_diaria_activa is True

    usuario = app.test_client()
    _loguear(usuario, app, 'prod_11')  # administrador del negocio, no root
    csrf = re.search(r'id="csrf-token" value="([^"]+)"', usuario.get('/gastronomia/pos').get_data(as_text=True)).group(1)
    resp = usuario.post(f'/usuarios/modulos-sistema/pasteleria/{cliente_id}/produccion', data={'csrf_token': csrf})
    assert resp.status_code == 403
    with app.app_context():
        assert GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one().produccion_diaria_activa is True
