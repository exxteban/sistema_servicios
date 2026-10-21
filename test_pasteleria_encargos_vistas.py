"""Fase 1 (paso 7) del plan de pasteleria: lo que ven cocina, caja y el listado operativo de un encargo."""
from datetime import timedelta

from app import create_app, db
from app.models import Usuario
from app.utils.helpers import now_local
from gastronomia.models import GastronomiaClienteConfig
from gastronomia.services.adelanto_service import registrar_adelanto
from gastronomia.services.encargo_service import crear_encargo, enviar_a_produccion
from gastronomia.services.pedido_service import crear_pedido
from test_gastronomia_caja import _abrir_caja, _loguear
from test_gastronomia_pedidos import _crear_menu_para_pedidos


CLAVES_DE_DINERO = {'sena_vigente', 'saldo', 'adelantos', 'total', 'subtotal', 'pago'}


def _fecha():
    base = now_local().replace(tzinfo=None) + timedelta(days=3)
    return base.replace(hour=15, minute=0, second=0, microsecond=0)


def _local_con_encargo(app, nombre: str, username: str, *, con_sena=True):
    cliente_id, producto_id, _ = _crear_menu_para_pedidos(app, nombre, username)
    with app.app_context():
        GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one().encargos_activo = True
        db.session.commit()
        usuario_id = Usuario.query.filter_by(username=username).first().id_usuario
    _abrir_caja(app, username)
    with app.app_context():
        encargo = crear_encargo(cliente_id, usuario_id, {
            'nombre_cliente': 'Ana',
            'fecha_programada': _fecha(),
            'items': [{'producto_id': producto_id, 'cantidad': 2, 'notas': 'Feliz cumple Ana'}],
        })
        if con_sena:
            registrar_adelanto(cliente_id, usuario_id, encargo.id_pedido, {'monto': 10000})
        return cliente_id, usuario_id, producto_id, encargo.id_pedido


def _claves(valor) -> set:
    if isinstance(valor, list):
        return set().union(*(_claves(item) for item in valor)) if valor else set()
    if isinstance(valor, dict):
        return set(valor) | set().union(*(_claves(item) for item in valor.values()))
    return set()


def test_cocina_no_ve_el_encargo_abierto_y_lo_ve_sin_montos_al_enviarlo():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, _, _, pedido_id = _local_con_encargo(app, 'Vista Enc 1', 'vista_enc_1')
    _loguear(client, app, 'vista_enc_1')

    pedidos = client.get('/api/gastronomia/cocina/pedidos').get_json()['pedidos']
    assert pedido_id not in [p['id_pedido'] for p in pedidos]

    with app.app_context():
        enviar_a_produccion(cliente_id, pedido_id)

    pedidos = client.get('/api/gastronomia/cocina/pedidos').get_json()['pedidos']
    encargo = next(p for p in pedidos if p['id_pedido'] == pedido_id)
    assert encargo['es_encargo'] is True
    assert encargo['fecha_programada']
    assert encargo['items'][0]['notas'] == 'Feliz cumple Ana'
    assert not (_claves(encargo) & CLAVES_DE_DINERO)


def test_listado_operativo_excluye_encargos_salvo_pedido_explicito():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, usuario_id, producto_id, pedido_id = _local_con_encargo(app, 'Vista Enc 2', 'vista_enc_2')
    _loguear(client, app, 'vista_enc_2')
    with app.app_context():
        normal = crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_id, 'cantidad': 1}],
        }).id_pedido

    ids = [p['id_pedido'] for p in client.get('/api/gastronomia/pedidos').get_json()['pedidos']]
    assert ids == [normal]
    ids = [p['id_pedido'] for p in client.get('/api/gastronomia/pedidos?incluir_encargos=1').get_json()['pedidos']]
    assert set(ids) == {normal, pedido_id}


def test_pedido_comun_serializa_sin_claves_de_encargo():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, usuario_id, producto_id, _ = _local_con_encargo(app, 'Vista Enc 3', 'vista_enc_3')
    _loguear(client, app, 'vista_enc_3')
    with app.app_context():
        normal = crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_id, 'cantidad': 1}],
        }).id_pedido

    pedido = client.get(f'/api/gastronomia/pedidos/{normal}').get_json()['pedido']
    assert pedido['es_encargo'] is False
    assert pedido['fecha_programada'] is None
    assert not ({'sena_vigente', 'saldo'} & set(pedido))
    listado = client.get('/api/gastronomia/pedidos').get_json()['pedidos'][0]
    assert listado['es_encargo'] is False
    assert not ({'sena_vigente', 'saldo'} & set(listado))


def test_encargo_expone_sena_y_saldo_al_operador():
    app = create_app('testing')
    client = app.test_client()
    _, _, _, pedido_id = _local_con_encargo(app, 'Vista Enc 4', 'vista_enc_4')
    _loguear(client, app, 'vista_enc_4')

    pedido = client.get(f'/api/gastronomia/pedidos/{pedido_id}').get_json()['pedido']
    assert pedido['es_encargo'] is True
    assert pedido['sena_vigente'] == 10000
    assert pedido['saldo'] == 20000
    listado = client.get('/api/gastronomia/pedidos?incluir_encargos=1').get_json()['pedidos'][0]
    assert (listado['sena_vigente'], listado['saldo']) == (10000, 20000)


def test_encargo_no_se_edita_por_la_ruta_generica_ni_desde_el_pos():
    app = create_app('testing')
    client = app.test_client()
    _, _, producto_id, pedido_id = _local_con_encargo(app, 'Vista Enc 5', 'vista_enc_5', con_sena=False)
    _loguear(client, app, 'vista_enc_5')
    pos_html = client.get(f'/gastronomia/pos?pedido={pedido_id}', follow_redirects=True).get_data(as_text=True)
    assert 'Los encargos se editan desde la pantalla de encargos.' in pos_html

    import re
    csrf = re.search(r'id="csrf-token" value="([^"]+)"', pos_html).group(1)
    resp = client.put(
        f'/api/gastronomia/pedidos/{pedido_id}',
        json={'tipo_pedido': 'retiro', 'items': [{'producto_id': producto_id, 'cantidad': 1}]},
        headers={'X-CSRFToken': csrf},
    )
    assert resp.status_code == 400
    assert 'encargos' in resp.get_json()['mensaje']
