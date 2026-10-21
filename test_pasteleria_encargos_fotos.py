"""Fase 1 (paso 8) del plan de pasteleria: fotos de referencia de encargos."""
import io
import os
import re
from datetime import timedelta

from PIL import Image

from app import create_app, db
from app.models import Usuario
from app.utils.helpers import now_local
from gastronomia.encargo_models import GastronomiaPedidoFoto
from gastronomia.models import GastronomiaClienteConfig
from gastronomia.services.adelanto_service import cancelar_encargo
from gastronomia.services.encargo_service import crear_encargo, enviar_a_produccion
from test_gastronomia_caja import _loguear
from test_gastronomia_pedidos import _crear_menu_para_pedidos


def _png(nombre='torta.png', size=(64, 48)):
    buffer = io.BytesIO()
    Image.new('RGB', size, (200, 120, 80)).save(buffer, format='PNG')
    buffer.seek(0)
    return buffer, nombre


def _app(tmp_path):
    app = create_app('testing')
    app.static_folder = str(tmp_path)
    return app


def _local(app, nombre, username, *, encargos=True, max_fotos=None):
    cliente_id, producto_id, _ = _crear_menu_para_pedidos(app, nombre, username)
    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one()
        config.encargos_activo = True
        if max_fotos is not None:
            config.encargos_max_fotos = max_fotos
        db.session.commit()
        usuario_id = Usuario.query.filter_by(username=username).first().id_usuario
        fecha = (now_local().replace(tzinfo=None) + timedelta(days=3)).replace(hour=15, minute=0, second=0, microsecond=0)
        pedido_id = crear_encargo(cliente_id, usuario_id, {
            'nombre_cliente': 'Ana',
            'fecha_programada': fecha,
            'items': [{'producto_id': producto_id, 'cantidad': 2}],
        }).id_pedido
        if not encargos:
            GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one().encargos_activo = False
            db.session.commit()
    return cliente_id, usuario_id, pedido_id


def _cliente_http(app, username):
    client = app.test_client()
    _loguear(client, app, username)
    html = client.get('/gastronomia/pos').get_data(as_text=True)
    csrf = re.search(r'id="csrf-token" value="([^"]+)"', html).group(1)
    return client, csrf


def _subir(client, csrf, pedido_id, archivo=None):
    return client.post(
        f'/api/gastronomia/encargos/{pedido_id}/fotos',
        data={'foto': archivo or _png()},
        headers={'X-CSRFToken': csrf},
        content_type='multipart/form-data',
    )


def _ruta(tmp_path, url):
    return os.path.join(str(tmp_path), *url[len('/static/'):].split('/'))


def test_subir_foto_la_guarda_en_la_carpeta_de_encargos_del_cliente(tmp_path):
    app = _app(tmp_path)
    cliente_id, _, pedido_id = _local(app, 'Fotos 1', 'fotos_1')
    client, csrf = _cliente_http(app, 'fotos_1')

    resp = _subir(client, csrf, pedido_id)
    assert resp.status_code == 201
    url = resp.get_json()['foto']['url']
    assert url.startswith(f'/static/tienda_uploads/gastronomia/encargos/{cliente_id}/encargo_{cliente_id}_')
    assert url.endswith('.webp')
    assert os.path.isfile(_ruta(tmp_path, url))

    fotos = client.get(f'/api/gastronomia/encargos/{pedido_id}/fotos').get_json()['fotos']
    assert [f['url'] for f in fotos] == [url]
    pedido = client.get(f'/api/gastronomia/pedidos/{pedido_id}').get_json()['pedido']
    assert [f['url'] for f in pedido['fotos']] == [url]


def test_cocina_ve_las_fotos_del_encargo(tmp_path):
    app = _app(tmp_path)
    cliente_id, _, pedido_id = _local(app, 'Fotos 2', 'fotos_2')
    client, csrf = _cliente_http(app, 'fotos_2')
    url = _subir(client, csrf, pedido_id).get_json()['foto']['url']
    with app.app_context():
        enviar_a_produccion(cliente_id, pedido_id)

    pedidos = client.get('/api/gastronomia/cocina/pedidos').get_json()['pedidos']
    encargo = next(p for p in pedidos if p['id_pedido'] == pedido_id)
    assert [f['url'] for f in encargo['fotos']] == [url]
    assert 'sena_vigente' not in encargo and 'saldo' not in encargo


def test_respeta_el_tope_de_fotos(tmp_path):
    app = _app(tmp_path)
    _, _, pedido_id = _local(app, 'Fotos 3', 'fotos_3', max_fotos=2)
    client, csrf = _cliente_http(app, 'fotos_3')

    assert _subir(client, csrf, pedido_id).status_code == 201
    assert _subir(client, csrf, pedido_id).status_code == 201
    resp = _subir(client, csrf, pedido_id)
    assert resp.status_code == 400
    assert 'hasta 2' in resp.get_json()['mensaje']


def test_rechaza_archivos_que_no_son_imagen(tmp_path):
    app = _app(tmp_path)
    _, _, pedido_id = _local(app, 'Fotos 4', 'fotos_4')
    client, csrf = _cliente_http(app, 'fotos_4')

    falso = (io.BytesIO(b'esto no es una imagen'), 'torta.png')
    resp = _subir(client, csrf, pedido_id, falso)
    assert resp.status_code == 400
    assert 'imagen' in resp.get_json()['mensaje']
    resp = _subir(client, csrf, pedido_id, (io.BytesIO(b'%PDF-1.4'), 'torta.pdf'))
    assert resp.status_code == 400
    with app.app_context():
        assert GastronomiaPedidoFoto.query.count() == 0


def test_borrar_foto_elimina_el_archivo(tmp_path):
    app = _app(tmp_path)
    _, _, pedido_id = _local(app, 'Fotos 5', 'fotos_5')
    client, csrf = _cliente_http(app, 'fotos_5')
    foto = _subir(client, csrf, pedido_id).get_json()['foto']

    resp = client.delete(
        f'/api/gastronomia/encargos/{pedido_id}/fotos/{foto["id_foto"]}', headers={'X-CSRFToken': csrf},
    )
    assert resp.status_code == 200
    assert not os.path.exists(_ruta(tmp_path, foto['url']))
    with app.app_context():
        assert GastronomiaPedidoFoto.query.count() == 0


def test_un_cliente_no_ve_ni_borra_fotos_de_otro(tmp_path):
    app = _app(tmp_path)
    _, _, pedido_a = _local(app, 'Fotos 6A', 'fotos_6a')
    _local(app, 'Fotos 6B', 'fotos_6b')
    client_a, csrf_a = _cliente_http(app, 'fotos_6a')
    foto = _subir(client_a, csrf_a, pedido_a).get_json()['foto']

    client_b, csrf_b = _cliente_http(app, 'fotos_6b')
    assert client_b.get(f'/api/gastronomia/encargos/{pedido_a}/fotos').status_code == 404
    assert _subir(client_b, csrf_b, pedido_a).status_code == 404
    resp = client_b.delete(
        f'/api/gastronomia/encargos/{pedido_a}/fotos/{foto["id_foto"]}', headers={'X-CSRFToken': csrf_b},
    )
    assert resp.status_code == 404
    assert os.path.isfile(_ruta(tmp_path, foto['url']))


def test_con_encargos_apagados_no_se_suben_ni_listan_fotos(tmp_path):
    app = _app(tmp_path)
    _, _, pedido_id = _local(app, 'Fotos 7', 'fotos_7', encargos=False)
    client, csrf = _cliente_http(app, 'fotos_7')

    assert _subir(client, csrf, pedido_id).status_code == 404
    assert client.get(f'/api/gastronomia/encargos/{pedido_id}/fotos').status_code == 404


def test_cancelar_el_encargo_borra_sus_fotos(tmp_path):
    app = _app(tmp_path)
    cliente_id, usuario_id, pedido_id = _local(app, 'Fotos 8', 'fotos_8')
    client, csrf = _cliente_http(app, 'fotos_8')
    url = _subir(client, csrf, pedido_id).get_json()['foto']['url']

    with app.test_request_context():
        cancelar_encargo(cliente_id, usuario_id, pedido_id)
        assert GastronomiaPedidoFoto.query.filter_by(pedido_id=pedido_id).count() == 0
    assert not os.path.exists(_ruta(tmp_path, url))

    # Un encargo cancelado ya no admite fotos.
    assert _subir(client, csrf, pedido_id).status_code == 400
