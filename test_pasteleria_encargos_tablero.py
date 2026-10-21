"""Fase 1 (paso 9) del plan de pasteleria: tablero de encargos, su API y la tarjeta del dashboard."""
import re
from datetime import timedelta

from app import create_app, db
from app.models import MovimientoCaja, Rol, Usuario
from app.utils.helpers import now_local
from gastronomia.encargo_models import ADELANTO_DEVUELTO, GastronomiaPedidoAdelanto
from gastronomia.models import GastronomiaClienteConfig, GastronomiaPedido
from gastronomia.services.adelanto_service import registrar_adelanto
from gastronomia.services.encargo_service import crear_encargo
from gastronomia.services.encargo_tablero_service import tablero_encargos
from test_gastronomia_caja import _abrir_caja, _loguear
from test_gastronomia_pedidos import _crear_menu_para_pedidos


def _dia(dias: int, hora: int = 15):
    base = now_local().replace(tzinfo=None) + timedelta(days=dias)
    return base.replace(hour=hora, minute=0, second=0, microsecond=0)


def _local(app, nombre, username, *, encargos=True, caja=True):
    cliente_id, producto_id, _ = _crear_menu_para_pedidos(app, nombre, username)
    with app.app_context():
        GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one().encargos_activo = encargos
        db.session.commit()
        usuario_id = Usuario.query.filter_by(username=username).first().id_usuario
    if caja:
        _abrir_caja(app, username)
    return cliente_id, usuario_id, producto_id


def _http(app, username):
    client = app.test_client()
    _loguear(client, app, username)
    html = client.get('/gastronomia/pos').get_data(as_text=True)
    return client, re.search(r'id="csrf-token" value="([^"]+)"', html).group(1)


def _payload(producto_id, dias=3, **extra):
    return {
        'nombre_cliente': 'Ana',
        'celular_cliente': '0981 000 000',
        'fecha_programada': _dia(dias).strftime('%Y-%m-%dT%H:%M'),
        'items': [{'producto_id': producto_id, 'cantidad': 2, 'texto_personalizado': 'Feliz cumple Ana'}],
        **extra,
    }


def test_tablero_agrupa_por_dia_con_totales_y_vencidos():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(app, 'Tablero 1', 'tablero_1', caja=False)

    with app.test_request_context():  # el serializador arma URLs publicas de seguimiento
        for dias, cantidad in ((1, 3), (1, 2), (3, 1)):
            crear_encargo(cliente_id, usuario_id, {
                'nombre_cliente': 'Ana', 'fecha_programada': _dia(dias),
                'items': [{'producto_id': producto_id, 'cantidad': cantidad}],
            })
        viejo = crear_encargo(cliente_id, usuario_id, {
            'nombre_cliente': 'Beto', 'fecha_programada': _dia(2),
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        })
        db.session.get(GastronomiaPedido, viejo.id_pedido).fecha_programada = _dia(-2)
        db.session.commit()

        data = tablero_encargos(cliente_id, dias=7)
        assert len(data['dias']) == 7
        manana = data['dias'][1]
        assert manana['cantidad'] == 2
        assert manana['produccion'] == [{'producto': 'Clasica', 'cantidad': 5}]
        assert data['dias'][3]['cantidad'] == 1
        assert [e['id_pedido'] for e in data['vencidos']] == [viejo.id_pedido]


def test_crear_encargo_con_sena_en_efectivo_entra_a_caja():
    app = create_app('testing')
    _, _, producto_id = _local(app, 'Tablero 2', 'tablero_2')
    client, csrf = _http(app, 'tablero_2')

    resp = client.post(
        '/api/gastronomia/encargos',
        json=_payload(producto_id, sena={'monto': 10000, 'metodo_pago': 'efectivo'}),
        headers={'X-CSRFToken': csrf},
    )
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()
    assert data['aviso'] is None
    assert data['pedido']['es_encargo'] is True
    assert data['pedido']['sena_vigente'] == 10000
    assert data['pedido']['saldo'] == 20000
    assert data['pedido']['items'][0]['texto_personalizado'] == 'Feliz cumple Ana'
    with app.app_context():
        assert MovimientoCaja.query.filter_by(referencia_tipo='gastronomia_sena').count() == 1


def test_sin_caja_abierta_la_sena_se_rechaza_antes_de_crear_el_encargo():
    app = create_app('testing')
    _, _, producto_id = _local(app, 'Tablero 3', 'tablero_3', caja=False)
    client, csrf = _http(app, 'tablero_3')

    resp = client.post(
        '/api/gastronomia/encargos',
        json=_payload(producto_id, sena={'monto': 10000}),
        headers={'X-CSRFToken': csrf},
    )
    assert resp.status_code == 400
    assert 'caja' in resp.get_json()['mensaje']
    with app.app_context():
        assert GastronomiaPedido.query.filter_by(es_encargo=True).count() == 0

    # Sin sena, el mismo encargo se toma sin caja abierta.
    resp = client.post('/api/gastronomia/encargos', json=_payload(producto_id), headers={'X-CSRFToken': csrf})
    assert resp.status_code == 201


def test_sena_mayor_al_total_guarda_el_encargo_y_avisa():
    app = create_app('testing')
    _, _, producto_id = _local(app, 'Tablero 4', 'tablero_4')
    client, csrf = _http(app, 'tablero_4')

    resp = client.post(
        '/api/gastronomia/encargos',
        json=_payload(producto_id, sena={'monto': 99999}),
        headers={'X-CSRFToken': csrf},
    )
    assert resp.status_code == 201
    assert 'la sena no se registro' in resp.get_json()['aviso']
    with app.app_context():
        assert GastronomiaPedido.query.filter_by(es_encargo=True).count() == 1
        assert GastronomiaPedidoAdelanto.query.count() == 0


def test_editar_enviar_a_produccion_y_ver_en_cocina():
    app = create_app('testing')
    _, _, producto_id = _local(app, 'Tablero 5', 'tablero_5')
    client, csrf = _http(app, 'tablero_5')
    pedido_id = client.post(
        '/api/gastronomia/encargos', json=_payload(producto_id), headers={'X-CSRFToken': csrf},
    ).get_json()['pedido']['id_pedido']

    resp = client.put(
        f'/api/gastronomia/encargos/{pedido_id}',
        json={**_payload(producto_id), 'items': [{'producto_id': producto_id, 'cantidad': 4}]},
        headers={'X-CSRFToken': csrf},
    )
    assert resp.status_code == 200
    assert resp.get_json()['pedido']['total'] == 60000

    resp = client.post(f'/api/gastronomia/encargos/{pedido_id}/produccion', json={}, headers={'X-CSRFToken': csrf})
    assert resp.status_code == 200
    cocina = client.get('/api/gastronomia/cocina/pedidos').get_json()['pedidos']
    assert pedido_id in [p['id_pedido'] for p in cocina]

    # Ya en produccion no se puede volver a enviar ni editar.
    assert client.post(
        f'/api/gastronomia/encargos/{pedido_id}/produccion', json={}, headers={'X-CSRFToken': csrf},
    ).status_code == 400


def test_cancelar_con_sena_exige_elegir_y_devuelve():
    app = create_app('testing')
    _, _, producto_id = _local(app, 'Tablero 6', 'tablero_6')
    client, csrf = _http(app, 'tablero_6')
    pedido_id = client.post(
        '/api/gastronomia/encargos',
        json=_payload(producto_id, sena={'monto': 10000}),
        headers={'X-CSRFToken': csrf},
    ).get_json()['pedido']['id_pedido']

    resp = client.post(f'/api/gastronomia/encargos/{pedido_id}/cancelar', json={}, headers={'X-CSRFToken': csrf})
    assert resp.status_code == 400
    assert 'Elegi' in resp.get_json()['mensaje']

    resp = client.post(
        f'/api/gastronomia/encargos/{pedido_id}/cancelar',
        json={'opcion': 'devolver_todo', 'motivo': 'Se suspendio el cumple'},
        headers={'X-CSRFToken': csrf},
    )
    assert resp.status_code == 200
    assert resp.get_json()['pedido']['estado'] == 'cancelado'
    with app.app_context():
        assert GastronomiaPedidoAdelanto.query.one().estado == ADELANTO_DEVUELTO


def test_sin_permiso_de_caja_no_se_resuelve_una_sena():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(app, 'Tablero 7', 'tablero_7')
    with app.app_context():
        pedido_id = crear_encargo(cliente_id, usuario_id, {
            'nombre_cliente': 'Ana', 'fecha_programada': _dia(3),
            'items': [{'producto_id': producto_id, 'cantidad': 2}],
        }).id_pedido
        registrar_adelanto(cliente_id, usuario_id, pedido_id, {'monto': 10000})
        mozo = Usuario(
            id_cliente=cliente_id, username='tablero_7_mozo', nombre_completo='Mozo',
            id_rol=Rol.query.filter_by(nombre='Mozo').one().id_rol, activo=True,
        )
        mozo.set_password('clave123')
        db.session.add(mozo)
        db.session.commit()

    client, csrf = _http(app, 'tablero_7_mozo')
    assert client.get('/api/gastronomia/encargos').status_code == 200
    resp = client.post(
        f'/api/gastronomia/encargos/{pedido_id}/cancelar',
        json={'opcion': 'retener_todo'},
        headers={'X-CSRFToken': csrf},
    )
    assert resp.status_code == 403


def test_pantalla_y_tarjeta_solo_con_el_flag():
    app = create_app('testing')
    cliente_id, _, _ = _local(app, 'Tablero 8', 'tablero_8', encargos=False, caja=False)
    client, _ = _http(app, 'tablero_8')

    assert client.get('/api/gastronomia/encargos').status_code == 404
    assert client.get('/gastronomia/encargos').status_code == 302
    assert 'data-dashboard-card-id="encargos"' not in client.get('/gastronomia/').get_data(as_text=True)

    with app.app_context():
        GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one().encargos_activo = True
        db.session.commit()
    assert 'data-dashboard-card-id="encargos"' in client.get('/gastronomia/').get_data(as_text=True)
    page = client.get('/gastronomia/encargos')
    assert page.status_code == 200
    assert 'id="encargo-form-dialog"' in page.get_data(as_text=True)
