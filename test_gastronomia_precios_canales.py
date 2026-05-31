import re
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app import create_app, db
from app.models import Cliente, Usuario
from config import TestingConfig, config
from gastronomia.channel_models import GastronomiaProductoPrecioCanal
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaPedidoItem,
    GastronomiaProducto,
)
from sqlalchemy import text


def _loguear(client, app, username: str):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        user_id = usuario.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def _csrf(html: str) -> str:
    match = re.search(r'id="csrf-token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _crear_restaurante(app, nombre: str, username: str) -> int:
    with app.app_context():
        cliente = Cliente(nombre=nombre, ruc_ci=username, tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(
            id_cliente=cliente.id_cliente,
            username=username,
            nombre_completo=f'Admin {nombre}',
            id_rol=1,
            activo=True,
        )
        usuario.set_password('clave123')
        db.session.add(usuario)
        db.session.add(GastronomiaClienteConfig(
            cliente_id=cliente.id_cliente,
            modo_operacion='gastronomia',
            gastronomia_activo=True,
        ))
        db.session.commit()
        return cliente.id_cliente


def _crear_producto(app, cliente_id: int, nombre: str = 'Hamburguesa canal') -> int:
    with app.app_context():
        categoria = GastronomiaCategoria(cliente_id=cliente_id, nombre=f'Combos {nombre}')
        db.session.add(categoria)
        db.session.flush()
        producto = GastronomiaProducto(
            cliente_id=cliente_id,
            categoria_id=categoria.id_categoria,
            nombre=nombre,
            precio=25000,
            disponible=True,
            visible=True,
            activo=True,
        )
        db.session.add(producto)
        db.session.commit()
        return producto.id_producto


def test_menu_muestra_accesos_y_pestanas_de_precios_externos():
    app = create_app('testing')
    client = app.test_client()
    cliente_id = _crear_restaurante(app, 'Resto Canales UI', 'resto_canales_ui')
    producto_id = _crear_producto(app, cliente_id)
    _loguear(client, app, 'resto_canales_ui')

    html_menu = client.get('/gastronomia/menu').get_data(as_text=True)
    html_pos = client.get('/gastronomia/pos').get_data(as_text=True)

    assert 'data-menu-tab="pedidosya"' in html_menu
    assert 'data-menu-tab="monchis"' in html_menu
    assert 'Precios exclusivos de PedidosYa' in html_menu
    assert 'Precios exclusivos de Monchis' in html_menu
    assert 'data-price-channel="pedidosya"' in html_pos
    assert 'data-price-channel="monchis"' in html_pos
    with app.app_context():
        precios = GastronomiaProductoPrecioCanal.query.filter_by(producto_id=producto_id).all()
        assert {item.canal: float(item.precio) for item in precios} == {
            'pedidosya': 25000,
            'monchis': 25000,
        }


def test_api_precio_canal_es_independiente_y_se_aplica_al_pedido():
    app = create_app('testing')
    client = app.test_client()
    cliente_id = _crear_restaurante(app, 'Resto Canales Pedido', 'resto_canales_pedido')
    producto_id = _crear_producto(app, cliente_id, 'Lomito canal')
    _loguear(client, app, 'resto_canales_pedido')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))

    response = client.put(
        f'/api/gastronomia/precios-canales/pedidosya/{producto_id}',
        json={'precio': '32.000'},
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 200
    assert response.get_json()['precio_canal']['precio'] == 32000

    with app.app_context():
        producto = db.session.get(GastronomiaProducto, producto_id)
        categoria_id = producto.categoria_id
    actualizar_normal = client.put(
        f'/api/gastronomia/productos/{producto_id}',
        json={
            'categoria_id': categoria_id,
            'nombre': 'Lomito canal',
            'precio': '27000',
            'disponible': True,
            'visible': True,
        },
        headers={'X-CSRFToken': csrf},
    )
    assert actualizar_normal.status_code == 200

    pedidosya = client.get('/api/gastronomia/productos', query_string={
        'publico': '1',
        'agotados': '1',
        'canal_precio': 'pedidosya',
    }).get_json()['productos'][0]
    monchis = client.get('/api/gastronomia/productos', query_string={
        'publico': '1',
        'agotados': '1',
        'canal_precio': 'monchis',
    }).get_json()['productos'][0]
    normal = client.get('/api/gastronomia/productos', query_string={
        'publico': '1',
        'agotados': '1',
    }).get_json()['productos'][0]
    assert pedidosya['precio'] == 32000
    assert pedidosya['canal_precio'] == 'pedidosya'
    assert monchis['precio'] == 25000
    assert normal['precio'] == 27000

    canal_invalido = client.get('/api/gastronomia/productos', query_string={'canal_precio': 'otro'})
    assert canal_invalido.status_code == 400

    pedido = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mostrador',
            'items': [{'producto_id': producto_id, 'cantidad': 2, 'canal_precio': 'pedidosya'}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido.status_code == 201
    pedido_data = pedido.get_json()['pedido']
    assert pedido_data['subtotal'] == 64000
    assert pedido_data['items'][0]['canal_precio'] == 'pedidosya'
    assert pedido_data['items'][0]['precio_unitario'] == 32000
    with app.app_context():
        item = GastronomiaPedidoItem.query.filter_by(producto_id=producto_id).order_by(
            GastronomiaPedidoItem.id_item.desc(),
        ).first()
        assert item.canal_precio == 'pedidosya'
        assert float(item.precio_unitario) == 32000


def test_api_precio_canal_respeta_cliente_de_sesion():
    app = create_app('testing')
    client = app.test_client()
    cliente_uno_id = _crear_restaurante(app, 'Resto Canal Uno', 'resto_canal_uno')
    cliente_dos_id = _crear_restaurante(app, 'Resto Canal Dos', 'resto_canal_dos')
    producto_uno_id = _crear_producto(app, cliente_uno_id, 'Producto privado canal')
    _crear_producto(app, cliente_dos_id, 'Producto propio canal')
    _loguear(client, app, 'resto_canal_dos')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))

    response = client.put(
        f'/api/gastronomia/precios-canales/monchis/{producto_uno_id}',
        json={'precio': '99999'},
        headers={'X-CSRFToken': csrf},
    )

    assert response.status_code == 404


def test_api_pedido_no_permite_mezclar_listas_de_precios():
    app = create_app('testing')
    client = app.test_client()
    cliente_id = _crear_restaurante(app, 'Resto Canales Mixtos', 'resto_canales_mixtos')
    producto_uno_id = _crear_producto(app, cliente_id, 'Producto normal')
    producto_dos_id = _crear_producto(app, cliente_id, 'Producto PedidosYa')
    _loguear(client, app, 'resto_canales_mixtos')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))

    response = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mostrador',
            'items': [
                {'producto_id': producto_uno_id, 'cantidad': 1},
                {'producto_id': producto_dos_id, 'cantidad': 1, 'canal_precio': 'pedidosya'},
            ],
        },
        headers={'X-CSRFToken': csrf},
    )

    assert response.status_code == 400
    assert 'no puede mezclar precios normales' in response.get_json()['mensaje']


def test_schema_actualiza_sqlite_existente_con_precios_por_canal():
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / 'legacy.sqlite3'
        connection = sqlite3.connect(db_path)
        try:
            connection.execute('CREATE TABLE gastronomia_pedido_items (id_item INTEGER PRIMARY KEY)')
            connection.commit()
        finally:
            connection.close()

        class LegacyTestingConfig(TestingConfig):
            SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path.as_posix()}'

        config_name = 'testing_gastronomia_channel_legacy'
        config[config_name] = LegacyTestingConfig
        try:
            app = create_app(config_name)
            with app.app_context():
                engine = db.engine
                item_columns = {
                    row[1]
                    for row in db.session.execute(text('PRAGMA table_info(gastronomia_pedido_items)')).fetchall()
                }
                tables = {
                    row[1]
                    for row in db.session.execute(text('PRAGMA table_list')).fetchall()
                }
                db.session.remove()
            engine.dispose()
        finally:
            config.pop(config_name, None)

    assert 'canal_precio' in item_columns
    assert 'gastronomia_producto_precios_canal' in tables
