import re

import pytest

from app import db
from app.models import Cliente, Usuario, Rol
from gastronomia.models import GastronomiaProducto
from gastronomia.channel_models import GastronomiaProductoPrecioCanal as PrecioCanal
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaConfig as Config, GastronomiaSugerenciaRegla as Regla,
    GastronomiaSugerenciaOrigen as Origen, GastronomiaSugerenciaPar as Par,
)
from gastronomia.routes.sugerencias_api_routes import _ids
from test_gastronomia_sugerencias_admin import pantalla  # noqa: F401
from test_gastronomia_menu import _loguear
from test_gastronomia_caja import _abrir_caja


def activar(pantalla):
    app, _, cliente, ids = pantalla
    with app.app_context():
        db.session.add(Config(cliente_id=cliente, activo=True, mostrar_en_pos=True, max_franja=2))
        db.session.add(Regla(cliente_id=cliente, origen_tipo='producto', origen_id=ids[0],
                             destino_tipo='producto', destino_id=ids[1]))
        db.session.commit()


def test_apagado_no_consulta_motor_ni_crea_config(pantalla, monkeypatch):
    app, client, cliente, ids = pantalla
    def inesperado(*args, **kwargs):
        pytest.fail('No debe consultar candidatos cuando está apagado')
    monkeypatch.setattr('gastronomia.routes.sugerencias_api_routes.previsualizar', inesperado)
    resp = client.get(f'/api/gastronomia/sugerencias?productos={ids[0]}')
    assert resp.status_code == 200
    assert resp.get_json() == {'ok': True, 'max': 0, 'sugerencias': []}
    assert resp.headers['Cache-Control'] == 'no-store'
    assert 'data-pos-sugerencias' not in client.get('/gastronomia/pos').get_data(as_text=True)
    with app.app_context():
        assert Config.query.filter_by(cliente_id=cliente).count() == 0


def test_endpoint_contrato_y_no_repite_producto(pantalla):
    _, client, _, ids = pantalla
    activar(pantalla)
    datos = client.get(f'/api/gastronomia/sugerencias?productos={ids[0]}').get_json()
    assert datos['max'] == 2
    assert datos['sugerencias'] == [dict(id_producto=ids[1], id_origen=ids[0],
                                       fuente='regla', motivo='Regla del negocio')]
    assert client.get(f'/api/gastronomia/sugerencias?productos={ids[0]},{ids[1]}').get_json()['sugerencias'] == []
    assert client.get('/api/gastronomia/sugerencias?productos=abc,-1,0,9999999999999999999999').get_json()['sugerencias'] == []
    html = client.get('/gastronomia/pos').get_data(as_text=True)
    assert 'data-pos-sugerencias' in html
    assert html.index('js/pos_sugerencias.js') < html.index('js/pos.js')


def test_precio_canal_filtra_sin_modificar_producto(pantalla):
    app, client, cliente, ids = pantalla
    activar(pantalla)
    with app.app_context():
        Regla.query.filter_by(cliente_id=cliente).delete()
        db.session.add(Origen(cliente_id=cliente, nivel='producto', id_origen=ids[0], pedidos=12))
        db.session.add(Par(cliente_id=cliente, nivel='producto', id_origen=ids[0], id_destino=ids[1],
                           soporte=6, confianza=.5, lift=2, puntaje=.3))
        db.session.add_all([PrecioCanal(cliente_id=cliente, producto_id=ids[0], canal='pedidosya', precio=10000),
                            PrecioCanal(cliente_id=cliente, producto_id=ids[1], canal='pedidosya', precio=20000)])
        db.session.commit()
    assert client.get(f'/api/gastronomia/sugerencias?productos={ids[0]}').get_json()['sugerencias']
    assert client.get(f'/api/gastronomia/sugerencias?productos={ids[0]}&canal_precio=pedidosya').get_json()['sugerencias'] == []
    assert client.get(f'/api/gastronomia/sugerencias?productos={ids[0]}&canal_precio=invalido').get_json()['sugerencias'] == []
    with app.app_context():
        assert float(db.session.get(GastronomiaProducto, ids[1]).precio) == 10000


def test_presupuesto_agotado_devuelve_vacio(pantalla, monkeypatch):
    activar(pantalla)
    monkeypatch.setattr('gastronomia.services.sugerencias.constantes.PRESUPUESTO_POS_SEGUNDOS', -1)
    _, client, _, ids = pantalla
    respuesta = client.get(f'/api/gastronomia/sugerencias?productos={ids[0]}')
    assert respuesta.status_code == 200
    assert respuesta.get_json()['sugerencias'] == []


def test_error_sugeridor_no_impide_guardar_cobrar_y_enviar(pantalla, monkeypatch):
    app, client, _, ids = pantalla
    activar(pantalla)
    def fallar(*args, **kwargs):
        raise RuntimeError('Fallo simulado del sugeridor')
    monkeypatch.setattr('gastronomia.routes.sugerencias_api_routes.previsualizar', fallar)
    assert client.get(f'/api/gastronomia/sugerencias?productos={ids[0]}').get_json()['sugerencias'] == []
    _abrir_caja(app, 'admin_sugerencias')
    html = client.get('/gastronomia/pos').get_data(as_text=True)
    token = re.search(r'id="csrf-token" value="([^"]+)"', html).group(1)
    headers = {'X-CSRFToken': token}
    guardar = client.post('/api/gastronomia/pedidos', json=dict(tipo_pedido='mostrador',
                          items=[dict(producto_id=ids[0], cantidad=1)]), headers=headers)
    assert guardar.status_code == 201
    pedido = guardar.get_json()['pedido']['id_pedido']
    cobro = client.post(f'/api/gastronomia/caja/pedidos/{pedido}/cobrar', json=dict(metodo_pago='efectivo'), headers=headers)
    assert cobro.status_code == 200
    assert cobro.get_json()['pedido']['estado_pago'] == 'pagado'
    cocina = client.post(f'/api/gastronomia/pedidos/{pedido}/enviar-cocina', json={}, headers=headers)
    assert cocina.status_code == 200


def test_aislamiento_y_permiso_pos(pantalla):
    app, client, _, ids = pantalla
    activar(pantalla)
    with app.app_context():
        otro = Cliente(nombre='Otro', ruc_ci='pos-otro')
        rol = Rol(nombre='Sin acceso al POS de sugerencias')
        db.session.add(otro)
        db.session.add(rol)
        db.session.flush()
        db.session.add(Usuario(username='otro_sugerencias_pos', nombre_completo='Otro',
                              id_cliente=otro.id_cliente, id_rol=1, password_hash='x'))
        db.session.add(Usuario(username='sin_sugerencias_pos', nombre_completo='Sin permiso',
                              id_cliente=otro.id_cliente, id_rol=rol.id_rol, password_hash='x'))
        db.session.commit()
    _loguear(client, app, 'otro_sugerencias_pos')
    assert client.get(f'/api/gastronomia/sugerencias?productos={ids[0]}').get_json()['sugerencias'] == []
    _loguear(client, app, 'sin_sugerencias_pos')
    assert client.get('/api/gastronomia/sugerencias').status_code == 403
    assert app.test_client().get('/api/gastronomia/sugerencias').status_code in (302, 401)


def test_ids_tienen_tope_y_no_aceptan_signos_o_unicode():
    assert _ids('1,٢,-3,0,4') == [1, 4]
    assert len(_ids(','.join(str(i) for i in range(1, 100)))) == 60
