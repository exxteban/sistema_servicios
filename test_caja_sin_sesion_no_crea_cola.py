from app import create_app, db
from app.models import Categoria, Cliente, ColaCobro, Configuracion, Producto, SesionCaja, Usuario
from gastronomia.models import GastronomiaClienteConfig, GastronomiaPedido


def _login(client, user_id: int):
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def _cerrar_sesiones_usuario(user_id: int):
    SesionCaja.query.filter_by(id_usuario=int(user_id), estado='abierta').update({'estado': 'cerrada'})
    db.session.commit()


def _crear_producto_pos():
    categoria = Categoria.query.filter_by(nombre='QA Sin Caja').first()
    if categoria is None:
        categoria = Categoria(nombre='QA Sin Caja', activo=True)
        db.session.add(categoria)
        db.session.flush()
    producto = Producto(
        codigo='QA-SIN-CAJA-001',
        nombre='Producto sin caja',
        id_categoria=categoria.id_categoria,
        precio_compra=10000,
        precio_venta=45000,
        porcentaje_iva=10,
        stock_actual=10,
        stock_minimo=1,
        activo=True,
    )
    db.session.add(producto)
    db.session.commit()
    return producto


def test_enviar_venta_a_caja_sin_caja_abierta_no_crea_pendiente():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        Configuracion.establecer_bool('caja_flujo_enviado_desde_vendedor', True)
        _cerrar_sesiones_usuario(admin.id_usuario)
        producto = _crear_producto_pos()
        total_antes = ColaCobro.query.count()
        _login(client, admin.id_usuario)

        response = client.post('/ventas/enviar-a-caja', json={
            'id_cliente': 1,
            'id_usuario_vendedor': int(admin.id_usuario),
            'client_request_id': 'venta-sin-caja-no-cola',
            'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
        })

        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'abrir una caja' in data['error'].lower()
        assert data['redirect_url'] == '/caja/abrir'
        assert ColaCobro.query.count() == total_antes


def test_cobro_avanzado_gastronomia_sin_caja_abierta_no_crea_cola():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()
    with app.app_context():
        cliente = Cliente(nombre='Resto Sin Caja', ruc_ci='resto_sin_caja', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(
            id_cliente=cliente.id_cliente,
            username='resto_sin_caja',
            nombre_completo='Resto Sin Caja',
            id_rol=1,
            activo=True,
        )
        usuario.set_password('clave123')
        db.session.add_all([
            usuario,
            GastronomiaClienteConfig(
                cliente_id=cliente.id_cliente,
                modo_operacion='gastronomia',
                gastronomia_activo=True,
            ),
        ])
        db.session.flush()
        pedido = GastronomiaPedido(
            cliente_id=cliente.id_cliente,
            usuario_id=usuario.id_usuario,
            tipo_pedido='mostrador',
            estado='abierto',
            subtotal=35000,
            total=35000,
        )
        db.session.add(pedido)
        db.session.commit()
        _cerrar_sesiones_usuario(usuario.id_usuario)
        total_antes = ColaCobro.query.count()
        _login(client, usuario.id_usuario)

        response = client.post(
            f'/api/gastronomia/pedidos/{pedido.id_pedido}/cobro-avanzado',
            json={'enviar_cocina': True},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data['error'] == 'caja_no_abierta'
        assert data['redirect_url'] == '/caja/abrir'
        assert ColaCobro.query.count() == total_antes
