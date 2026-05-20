import io
import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from app import create_app, db
from app.models import Cliente, Producto, TiendaConfig, Usuario
from app.utils.imagenes import nombre_derivado_imagen, procesar_y_guardar_imagen
from flask import render_template


def _loguear_admin(client, app):
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        admin_id = admin.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(admin_id)
        session['_fresh'] = True


def _obtener_o_crear_config_tienda():
    config = TiendaConfig.query.first()
    if config:
        return config

    cliente = Cliente.query.order_by(Cliente.id_cliente.asc()).first()
    assert cliente is not None

    config = TiendaConfig(
        id_cliente=cliente.id_cliente,
        slug='demo-test',
        nombre_tienda='Tienda Demo',
        activa=True,
    )
    db.session.add(config)
    db.session.commit()
    return config


def test_panel_tienda_muestra_boton_de_estadisticas():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    response = client.get('/tienda-admin')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'abrirModalEstadisticasTienda()' in html
    assert '1 día' in html
    assert 'Ranking de productos más vistos' in html
    assert 'Evolución visitas vs consultas WhatsApp' in html
    assert 'Horarios pico' in html
    assert 'Navegadores' in html
    assert 'statsTiendaIngresos' not in html
    assert 'statsTiendaVentas' not in html


def test_panel_tienda_muestra_links_del_bot_cuando_hay_slug():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    with app.app_context():
        config = _obtener_o_crear_config_tienda()
        config.slug = 'demo-test'
        db.session.commit()

    response = client.get('/tienda-admin')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '/robot/demo-test' in html
    assert '/tienda/demo-test/asistente' not in html
    assert 'Links del asistente' in html
    assert 'Asistente en tienda' not in html
    assert 'modalLinkBotTienda' not in html


def test_panel_tienda_partial_en_tab_mantiene_barra_de_busqueda():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    response = client.get('/tienda-admin?partial=1&q=iphone', headers={'X-Requested-With': 'XMLHttpRequest'})

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'partial-content' in html
    assert 'Mi Tienda Online' in html
    assert 'tienda-admin-search-form' in html
    assert 'Acciones' in html


def test_panel_tienda_fragmento_productos_devuelve_solo_resultados():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    response = client.get('/tienda-admin?partial=1&fragment=productos&q=iphone', headers={'X-Requested-With': 'XMLHttpRequest'})

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Mi Tienda Online' not in html
    assert 'Acciones' in html
    assert 'tienda-admin-search-form' not in html


def test_panel_tienda_ignora_partial_en_carga_normal():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    response = client.get('/tienda-admin?partial=1&q=iphone')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Mi Tienda Online' in html
    assert 'tienda-admin-search-form' in html


def test_panel_productos_standalone_muestra_barra_en_carga_normal():
    app = create_app('testing')

    with app.app_context():
        productos = Producto.query.order_by(Producto.nombre.asc()).paginate(page=1, per_page=20, error_out=False)

        with app.test_request_context('/tienda-admin?partial=1&q=iphone'):
            html = render_template('tienda_admin/_panel_productos.html', productos=productos, q='iphone')

        with app.test_request_context('/tienda-admin?partial=1&q=iphone', headers={'X-Requested-With': 'XMLHttpRequest'}):
            html_ajax = render_template('tienda_admin/_panel_productos.html', productos=productos, q='iphone')

    assert 'placeholder="Buscar productos..."' in html
    assert 'placeholder="Buscar productos..."' not in html_ajax


def test_api_estadisticas_tienda_devuelve_resumen_y_paginacion():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    payload = {
        'desde': '2026-03-01',
        'hasta': '2026-03-25',
        'periodo_anterior': {
            'desde': '2026-02-05',
            'hasta': '2026-02-28',
        },
        'summary': {
            'total_visitas': 42,
            'visitantes_unicos': 18,
            'leads_generados': 6,
            'productos_con_visitas': 4,
            'conversion_global': 14.29,
        },
        'ranking': [{
            'id_producto': 10,
            'nombre': 'Producto demo',
            'codigo': 'SKU-1',
            'categoria': 'Accesorios',
            'total_visitas': 20,
            'visitantes_unicos': 9,
            'leads_generados': 3,
            'conversion_leads': 15.0,
            'visitas_periodo_anterior': 12,
            'tendencia_direccion': 'up',
            'tendencia_porcentaje': 66.67,
        }],
        'chart': {
            'labels': ['Producto demo'],
            'values': [20],
        },
        'insights': {
            'horarios_pico': [{'hora': '10:00', 'total_visitas': 11}],
            'categorias_populares': [{'categoria': 'Accesorios', 'total_visitas': 20}],
            'dispositivos': [{'label': 'Móvil', 'value': 15}],
            'navegadores': [{'label': 'Chrome', 'value': 14}],
        },
        'evolution': {
            'labels': ['2026-03-01'],
            'visitas': [20],
            'consultas': [2],
        },
        'pagination': {
            'page': 2,
            'per_page': 7,
            'total_items': 15,
            'total_pages': 3,
            'has_prev': True,
            'has_next': True,
        },
    }

    with patch('app.routes.tienda_api._resolver_id_cliente_actual', return_value=77), patch(
        'app.routes.tienda_api.obtener_resumen_estadisticas_tienda',
        return_value=payload,
    ) as mock_service:
        response = client.get('/api/tienda/admin/estadisticas/productos-mas-vistos?range=month&page=2&per_page=7&categoria_id=3')

    assert response.status_code == 200
    data = response.get_json()
    assert data['ok'] is True
    assert data['range'] == 'month'
    assert data['categoria_id'] == 3
    assert data['summary']['total_visitas'] == 42
    assert data['pagination']['page'] == 2
    assert data['ranking'][0]['nombre'] == 'Producto demo'
    assert data['ranking'][0]['leads_generados'] == 3
    assert data['insights']['navegadores'][0]['label'] == 'Chrome'
    assert data['evolution']['consultas'] == [2]

    kwargs = mock_service.call_args.kwargs
    assert kwargs['id_cliente'] == 77
    assert kwargs['categoria_id'] == 3
    assert kwargs['page'] == 2
    assert kwargs['per_page'] == 7


def test_api_tienda_lead_rechaza_honeypot():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        config = _obtener_o_crear_config_tienda()
        slug = config.slug

    response = client.post(
        '/api/tienda/lead',
        json={
            'slug': slug,
            'nombre': 'Cliente Real',
            'telefono': '3001234567',
            'website': 'https://spam.invalid',
        },
    )

    assert response.status_code == 400
    assert response.get_json()['error'] == 'solicitud_invalida'


def test_api_tienda_lead_rate_limit_envia_retry_after_header():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        config = _obtener_o_crear_config_tienda()
        slug = config.slug

    with patch('app.routes.tienda_api._is_lead_rate_limited', return_value=(True, 57)):
        response = client.post(
            '/api/tienda/lead',
            json={
                'slug': slug,
                'nombre': 'Cliente Real',
                'telefono': '3001234567',
            },
        )

    assert response.status_code == 429
    assert response.headers['Retry-After'] == '57'
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.get_json()['retry_after'] == 57


def test_procesar_y_guardar_imagen_rechaza_pixeles_excesivos():
    fake_image = Image.new('RGB', (10001, 10001), color='white')
    contenido = io.BytesIO()
    fake_image.save(contenido, format='PNG')
    contenido.seek(0)

    with TemporaryDirectory() as temp_dir:
        try:
            procesar_y_guardar_imagen(contenido, temp_dir)
        except ValueError as exc:
            assert str(exc) == 'imagen_demasiado_grande'
        else:
            raise AssertionError('Se esperaba ValueError para imágenes demasiado grandes')


def test_procesar_y_guardar_imagen_crea_derivado_card_webp():
    fake_image = Image.new('RGB', (900, 700), color='white')
    contenido = io.BytesIO()
    fake_image.save(contenido, format='JPEG')
    contenido.seek(0)

    with TemporaryDirectory() as temp_dir:
        nombre = procesar_y_guardar_imagen(contenido, temp_dir, prefijo='prod_1', generar_card=True)
        nombre_card = nombre_derivado_imagen(nombre, 'card')
        ruta_card = os.path.join(temp_dir, nombre_card)

        assert os.path.isfile(ruta_card)
        with Image.open(ruta_card) as imagen_card:
            assert imagen_card.format == 'WEBP'
            assert imagen_card.width <= 480
            assert imagen_card.height <= 480
