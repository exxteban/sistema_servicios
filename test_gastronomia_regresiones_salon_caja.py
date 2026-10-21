"""Regresiones: renombrar mesa con cuenta abierta y delivery en camino sin cobrar."""
from app import create_app, db
from app.models import Usuario
from gastronomia.models import GastronomiaPedido
from gastronomia.services.caja_service import listar_pedidos_caja, resumen_pedidos_impagos_para_cierre
from gastronomia.services.pedido_service import cambiar_estado_pedido, crear_pedido
from test_gastronomia_pedidos import _crear_menu_para_pedidos
from test_gastronomia_salon import _crear_pedido_mesa, _crear_producto, _csrf, _loguear


def test_renombrar_mesa_ocupada_conserva_su_pedido_abierto():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, producto_id = _crear_producto(app, 'Resto Renombre', 'resto_renombre')
    _loguear(client, app, 'resto_renombre')
    csrf = _csrf(client.get('/gastronomia/salon').get_data(as_text=True))
    mesa_id = client.post(
        '/api/gastronomia/salon/mesas', json={'nombre': 'M1'}, headers={'X-CSRFToken': csrf},
    ).get_json()['mesa']['id_mesa']
    pedido_id = _crear_pedido_mesa(client, csrf, producto_id, 'M1')

    resp = client.put(
        f'/api/gastronomia/salon/mesas/{mesa_id}', json={'nombre': 'Terraza'}, headers={'X-CSRFToken': csrf},
    )
    assert resp.status_code == 200

    mesa = client.get('/api/gastronomia/salon/estado').get_json()['mesas'][0]
    assert mesa['nombre'] == 'Terraza'
    assert mesa['estado_salon'] == 'ocupada'
    assert mesa['pedido_activo']['id_pedido'] == pedido_id
    with app.app_context():
        assert db.session.get(GastronomiaPedido, pedido_id).mesa == 'Terraza'


def test_delivery_en_camino_sigue_pendiente_en_caja_y_en_cierre():
    app = create_app('testing')
    cliente_id, producto_id, _ = _crear_menu_para_pedidos(app, 'Resto Camino', 'resto_camino')
    with app.app_context():
        usuario_id = Usuario.query.filter_by(username='resto_camino').first().id_usuario
        pedido = crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'delivery',
            'celular_cliente': '0981000000',
            'direccion_entrega': 'Calle 1',
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        })
        cambiar_estado_pedido(cliente_id, pedido.id_pedido, 'listo')
        cambiar_estado_pedido(cliente_id, pedido.id_pedido, 'en_camino')

        assert pedido.id_pedido in [p.id_pedido for p in listar_pedidos_caja(cliente_id)]
        resumen = resumen_pedidos_impagos_para_cierre(cliente_id)
        assert [p['id_pedido'] for p in resumen['terminados']] == [pedido.id_pedido]
