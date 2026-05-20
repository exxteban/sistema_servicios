import unicodedata

from app import create_app, db
from app.models import Cliente, Configuracion, MetodoPago, SesionCaja, Usuario
from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO


def _loguear_admin(client):
    admin = Usuario.query.filter_by(username='admin').first()
    assert admin is not None
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin.id_usuario)
        sess['_fresh'] = True
    return admin


def _abrir_caja(admin):
    sesion = SesionCaja(
        id_caja=1,
        id_usuario=admin.id_usuario,
        monto_inicial=250000,
        estado='abierta',
    )
    db.session.add(sesion)
    db.session.commit()
    return sesion


def _crear_producto(precio, codigo='TEST-CRED-MODAL-001'):
    from app.models import Categoria, Producto

    categoria = Categoria.query.filter_by(nombre='Test Credito Modal UI').first()
    if categoria is None:
        categoria = Categoria(nombre='Test Credito Modal UI', activo=True)
        db.session.add(categoria)
        db.session.flush()

    producto = Producto(
        codigo=codigo,
        nombre='Producto Modal Credito',
        id_categoria=categoria.id_categoria,
        precio_compra=40000,
        precio_venta=precio,
        porcentaje_iva=10,
        stock_actual=10,
        stock_minimo=1,
        es_servicio=False,
        activo=True,
    )
    db.session.add(producto)
    db.session.commit()
    return producto


def _texto_simple(valor):
    normalizado = unicodedata.normalize('NFKD', valor or '')
    return ''.join(ch for ch in normalizado if not unicodedata.combining(ch)).strip().lower()


def _obtener_metodo_credito():
    for metodo in MetodoPago.query.all():
        if _texto_simple(metodo.nombre) == 'credito tienda':
            return metodo
    return None


def _obtener_metodo_efectivo():
    for metodo in MetodoPago.query.all():
        if _texto_simple(metodo.nombre) == 'efectivo':
            return metodo
    return None


def test_modal_ventas_muestra_campos_credito_en_listados_y_detalle_json():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    with app.app_context():
        admin = _loguear_admin(client)
        _abrir_caja(admin)
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        cliente = Cliente(
            nombre='Cliente Modal Credito',
            ruc_ci='8000888-1',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(cliente)
        db.session.commit()

        producto = _crear_producto(105000)
        metodo_credito = _obtener_metodo_credito()
        if metodo_credito is None:
            metodo_credito = MetodoPago.query.filter(MetodoPago.nombre.ilike('%Crédito Tienda%')).first()
        if metodo_credito is None:
            metodo_credito = MetodoPago.query.filter(MetodoPago.nombre.ilike('%Credito Tienda%')).first()
        assert metodo_credito is not None

        resp = client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(metodo_credito.id_metodo_pago), 'monto': 105000}],
                'id_cliente': int(cliente.id_cliente),
                'id_usuario_vendedor': int(admin.id_usuario),
                'client_request_id': 'venta-modal-credito-001',
            },
        )
        assert resp.status_code == 200
        venta_id = int((resp.get_json() or {})['id_venta'])

        detalle_resp = client.get(f'/reportes/ventas/{venta_id}/detalle')
        assert detalle_resp.status_code == 200
        detalle = detalle_resp.get_json() or {}
        assert detalle.get('tipo_venta') == 'Credito'
        assert detalle.get('estado_cobro') == 'Pendiente'
        assert float(detalle.get('cobrado_al_momento') or 0) == 0.0
        assert float(detalle.get('saldo_pendiente') or 0) > 0

        listar_html = client.get('/ventas/', follow_redirects=True).get_data(as_text=True)
        assert 'Tipo de venta' in listar_html
        assert "venta?.tipo_venta || 'Contado'" in listar_html
        assert "venta?.estado_cobro || 'Pendiente'" in listar_html
        assert "venta?.saldo_pendiente || 0" in listar_html

        ventas_diarias_html = client.get('/reportes/ventas-diarias', follow_redirects=True).get_data(as_text=True)
        assert 'Tipo de venta' in ventas_diarias_html
        assert "venta?.tipo_venta || 'Contado'" in ventas_diarias_html
        assert "venta?.estado_cobro || 'Pendiente'" in ventas_diarias_html
        assert "venta?.cobrado_al_momento || 0" in ventas_diarias_html


def test_ventas_diarias_muestran_cobro_real_y_deuda_credito():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    with app.app_context():
        admin = _loguear_admin(client)
        _abrir_caja(admin)
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        cliente = Cliente(
            nombre='Cliente Reporte Credito',
            ruc_ci='8000999-1',
            tipo='minorista',
            limite_credito=500000,
            activo=True,
        )
        db.session.add(cliente)
        db.session.commit()

        producto = _crear_producto(105000)
        metodo_credito = _obtener_metodo_credito()
        assert metodo_credito is not None

        resp = client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(metodo_credito.id_metodo_pago), 'monto': 105000}],
                'id_cliente': int(cliente.id_cliente),
                'id_usuario_vendedor': int(admin.id_usuario),
                'client_request_id': 'venta-modal-credito-002',
            },
        )
        assert resp.status_code == 200

        ventas_diarias_html = client.get('/reportes/ventas-diarias', follow_redirects=True).get_data(as_text=True)
        assert 'Cobrado del dia' in ventas_diarias_html
        assert 'Deuda credito generada' in ventas_diarias_html
        assert 'Ventas registradas' in ventas_diarias_html
        assert 'Caja solo considera cobros registrados' in ventas_diarias_html
        assert '105.000' in ventas_diarias_html
        assert 'Ventas emitidas del dia' not in ventas_diarias_html


def test_dashboard_totaliza_solo_cobros_reales_y_no_credito_emitido():
    from pedidos.models import PedidoCliente, PedidoClienteDetalle
    from pedidos.services.pago_service import registrar_pago_pedido
    from pedidos.services.pedido_service import recalcular_totales_pedido

    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    with app.app_context():
        admin = _loguear_admin(client)
        _abrir_caja(admin)
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        cliente = Cliente(
            nombre='Cliente Dashboard Credito',
            ruc_ci='8000777-1',
            tipo='minorista',
            limite_credito=800000,
            activo=True,
        )
        db.session.add(cliente)
        db.session.commit()

        producto_contado = _crear_producto(50000, codigo='TEST-CRED-MODAL-010')
        producto_credito = _crear_producto(120000, codigo='TEST-CRED-MODAL-011')
        producto_pedido = _crear_producto(70000, codigo='TEST-CRED-MODAL-012')
        metodo_efectivo = _obtener_metodo_efectivo()
        metodo_credito = _obtener_metodo_credito()
        assert metodo_efectivo is not None
        assert metodo_credito is not None

        resp_contado = client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto_contado.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(metodo_efectivo.id_metodo_pago), 'monto': 50000}],
                'id_cliente': int(cliente.id_cliente),
                'id_usuario_vendedor': int(admin.id_usuario),
                'client_request_id': 'dashboard-cobro-real-001',
            },
        )
        assert resp_contado.status_code == 200

        resp_credito = client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto_credito.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(metodo_credito.id_metodo_pago), 'monto': 120000}],
                'id_cliente': int(cliente.id_cliente),
                'id_usuario_vendedor': int(admin.id_usuario),
                'client_request_id': 'dashboard-cobro-real-002',
            },
        )
        assert resp_credito.status_code == 200

        pedido = PedidoCliente(
            id_cliente=int(cliente.id_cliente),
            id_usuario_creacion=int(admin.id_usuario),
            id_usuario_modificacion=int(admin.id_usuario),
            estado='pendiente_sena',
        )
        db.session.add(pedido)
        db.session.flush()
        db.session.add(PedidoClienteDetalle(
            id_pedido=int(pedido.id_pedido),
            id_producto=int(producto_pedido.id_producto),
            cantidad=1,
            precio_unitario=70000,
            porcentaje_iva=10,
            subtotal=70000,
            producto_codigo_snapshot=producto_pedido.codigo,
            producto_nombre_snapshot=producto_pedido.nombre,
        ))
        db.session.flush()
        recalcular_totales_pedido(pedido)
        registrar_pago_pedido(
            pedido,
            id_metodo_pago=int(metodo_efectivo.id_metodo_pago),
            monto=70000,
            tipo_pago='pago_total',
            id_usuario=int(admin.id_usuario),
            sesion=SesionCaja.query.filter_by(id_usuario=admin.id_usuario, estado='abierta').first(),
        )
        db.session.commit()

        dashboard_data = client.get('/api/dashboard/totales?range=hoy', follow_redirects=True).get_json() or {}
        assert float(dashboard_data.get('cobrado_en_ventas') or 0) == 50000.0
        assert float(dashboard_data.get('cobrado_en_creditos') or 0) == 0.0
        assert float(dashboard_data.get('cobrado_en_pedidos') or 0) == 70000.0
        assert float(dashboard_data.get('total_cobrado') or 0) == 120000.0

        dashboard_html = client.get('/', follow_redirects=True).get_data(as_text=True)
        assert 'Cobrado real' in dashboard_html
        assert 'Ventas cobradas:' in dashboard_html
        assert 'Creditos cobrados:' in dashboard_html
        assert 'Pedidos cobrados:' in dashboard_html
