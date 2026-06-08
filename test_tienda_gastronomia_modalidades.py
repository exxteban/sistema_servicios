from app import create_app, db
from app.models import Configuracion, Rol, Usuario
from gastronomia.models import GastronomiaPedido
from test_tienda_gastronomia_presupuesto import _crear_tienda_gastronomia, _loguear_admin
from gastronomia.services.modo_operacion import CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA, MODO_SERVICIOS


def test_tienda_gastronomia_respeta_modalidades_activas():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
        tienda, producto = _crear_tienda_gastronomia(slug='gastro-modalidades-test')
        tienda.tienda_delivery_activo = False
        tienda.tienda_retiro_activo = True
        admin = Usuario.query.filter_by(username='admin').first()
        admin.id_cliente = tienda.id_cliente
        db.session.commit()
        slug = tienda.slug
        producto_id = producto.id_producto

    try:
        config_response = client.get(f'/api/tienda/{slug}/config')
        assert config_response.status_code == 200
        config_data = config_response.get_json()
        assert config_data['tienda_delivery_activo'] is False
        assert config_data['tienda_retiro_activo'] is True

        delivery_response = client.post(f'/api/tienda/{slug}/gastronomia/pedido', json={
            'tipo_pedido': 'delivery',
            'nombre': 'Carlos Cliente',
            'celular': '0981123456',
            'direccion_entrega': 'Casa 123',
            'items': [{'id': producto_id, 'quantity': 1}],
        })
        assert delivery_response.status_code == 400
        assert delivery_response.get_json()['error'] == 'delivery_no_disponible'

        retiro_response = client.post(f'/api/tienda/{slug}/gastronomia/pedido', json={
            'tipo_pedido': 'retiro',
            'nombre': 'Carlos Cliente',
            'celular': '0981123456',
            'items': [{'id': producto_id, 'quantity': 1}],
        })
        assert retiro_response.status_code == 201
    finally:
        with app.app_context():
            Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)


def test_tienda_gastronomia_pedido_publico_usa_admin_si_no_hay_usuario_del_cliente():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
        tienda, producto = _crear_tienda_gastronomia(slug='gastro-admin-fallback-test')
        admin = Usuario.query.filter_by(username='admin').first()
        admin.id_cliente = None
        admin.activo = True
        db.session.commit()
        slug = tienda.slug
        producto_id = producto.id_producto

    try:
        response = client.post(f'/api/tienda/{slug}/gastronomia/pedido', json={
            'tipo_pedido': 'retiro',
            'nombre': 'Esteban',
            'celular': '0961862624',
            'referencia_entrega': '123',
            'items': [{'id': producto_id, 'quantity': 1}],
        })
        assert response.status_code == 201
        assert response.get_json()['pedido']['codigo_entrega']
    finally:
        with app.app_context():
            Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)


def test_tienda_gastronomia_pedido_publico_no_usa_root_como_receptor():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
        tienda, producto = _crear_tienda_gastronomia(slug='gastro-root-no-fallback-test')
        root_role = Rol.query.filter_by(nombre='Root').first()
        admin = Usuario.query.filter_by(username='admin').first()
        admin.activo = False
        root = Usuario.query.filter_by(username='root').first()
        root.activo = True
        if root_role:
            root.id_rol = root_role.id_rol
        root.id_cliente = None
        db.session.commit()
        slug = tienda.slug
        producto_id = producto.id_producto

    try:
        response = client.post(f'/api/tienda/{slug}/gastronomia/pedido', json={
            'tipo_pedido': 'retiro',
            'nombre': 'Esteban',
            'celular': '0961862624',
            'items': [{'id': producto_id, 'quantity': 1}],
        })
        assert response.status_code == 400
        assert 'administrador activo' in response.get_json()['mensaje']
    finally:
        with app.app_context():
            admin = Usuario.query.filter_by(username='admin').first()
            if admin:
                admin.activo = True
                db.session.commit()
            Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)


def test_pedido_tienda_queda_pendiente_hasta_confirmar_a_cocina():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
        tienda, producto = _crear_tienda_gastronomia(slug='gastro-pendiente-tienda-test')
        admin = Usuario.query.filter_by(username='admin').first()
        admin.id_cliente = tienda.id_cliente
        admin.activo = True
        db.session.commit()
        slug = tienda.slug
        producto_id = producto.id_producto
        cliente_id = tienda.id_cliente

    try:
        response = client.post(f'/api/tienda/{slug}/gastronomia/pedido', json={
            'tipo_pedido': 'delivery',
            'nombre': 'Cliente Web',
            'celular': '0981123456',
            'direccion_entrega': 'Casa 123',
            'items': [{'id': producto_id, 'quantity': 1}],
        })
        assert response.status_code == 201

        with app.app_context():
            pedido = GastronomiaPedido.query.filter_by(cliente_id=cliente_id).order_by(GastronomiaPedido.id_pedido.desc()).first()
            pedido_id = pedido.id_pedido
            assert pedido.origen_pedido == 'tienda_online'
            assert pedido.estado == 'abierto'
            assert pedido.fecha_envio_cocina is None

        _loguear_admin(client, app, cliente_id=cliente_id)
        tienda_response = client.get('/api/gastronomia/tienda/pedidos')
        assert tienda_response.status_code == 200
        assert [item['id_pedido'] for item in tienda_response.get_json()['pedidos']] == [pedido_id]

        cocina_response = client.get('/api/gastronomia/cocina/pedidos')
        assert cocina_response.status_code == 200
        assert cocina_response.get_json()['pedidos'] == []

        confirmar_response = client.post(f'/api/gastronomia/tienda/pedidos/{pedido_id}/confirmar')
        assert confirmar_response.status_code == 200

        cocina_confirmada = client.get('/api/gastronomia/cocina/pedidos')
        assert cocina_confirmada.status_code == 200
        assert [item['id_pedido'] for item in cocina_confirmada.get_json()['pedidos']] == [pedido_id]
    finally:
        with app.app_context():
            Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)
