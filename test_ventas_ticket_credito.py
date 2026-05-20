from datetime import date, timedelta

from app import create_app, db
from app.models import Categoria, Cliente, Configuracion, MetodoPago, Producto, SesionCaja, Usuario
from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO, CLAVE_VENTAS_CREDITO_METODO_PAGO_ID


def _login_admin(client):
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
        monto_inicial=150000,
        estado='abierta',
    )
    db.session.add(sesion)
    db.session.commit()
    return sesion


def _texto_simple(valor):
    return ''.join(ch for ch in (valor or '').lower().strip() if ch.isalnum() or ch.isspace())


def _metodo_por_nombre(nombre_objetivo):
    objetivo = _texto_simple(nombre_objetivo)
    for metodo in MetodoPago.query.all():
        nombre_normalizado = _texto_simple(metodo.nombre)
        if nombre_normalizado == objetivo:
            return metodo
        if objetivo == 'credito tienda' and 'credito' in nombre_normalizado and 'tienda' in nombre_normalizado:
            return metodo
    return None


def _crear_producto(precio, codigo):
    categoria = Categoria.query.filter_by(nombre='Test Ticket Credito').first()
    if categoria is None:
        categoria = Categoria(nombre='Test Ticket Credito', activo=True)
        db.session.add(categoria)
        db.session.flush()

    producto = Producto(
        codigo=codigo,
        nombre='Producto Ticket Credito',
        id_categoria=categoria.id_categoria,
        precio_compra=30000,
        precio_venta=precio,
        porcentaje_iva=10,
        stock_actual=8,
        stock_minimo=1,
        es_servicio=False,
        activo=True,
    )
    db.session.add(producto)
    db.session.commit()
    return producto


def _asegurar_metodo_credito():
    metodo = _metodo_por_nombre('credito tienda')
    if metodo is not None:
        return metodo
    metodo = MetodoPago(
        nombre='Credito Tienda',
        activo=True,
        orden_display=999,
    )
    db.session.add(metodo)
    db.session.commit()
    return metodo


def test_ticket_credito_preview_muestra_detalle_financiado_y_cuotas():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    with app.app_context():
        admin = _login_admin(client)
        _abrir_caja(admin)
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)

        cliente = Cliente(
            nombre='Cliente Ticket Credito',
            ruc_ci='8000555-1',
            tipo='minorista',
            limite_credito=900000,
            activo=True,
        )
        db.session.add(cliente)
        db.session.commit()

        producto = _crear_producto(120000, 'TEST-TICKET-CRED-001')
        metodo_efectivo = _metodo_por_nombre('efectivo')
        metodo_credito = _asegurar_metodo_credito()
        Configuracion.establecer(CLAVE_VENTAS_CREDITO_METODO_PAGO_ID, str(int(metodo_credito.id_metodo_pago)))
        assert metodo_efectivo is not None
        assert metodo_credito is not None

        response = client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [
                    {'id_metodo_pago': int(metodo_efectivo.id_metodo_pago), 'monto': 20000},
                    {'id_metodo_pago': int(metodo_credito.id_metodo_pago), 'monto': 100000},
                ],
                'id_cliente': int(cliente.id_cliente),
                'id_usuario_vendedor': int(admin.id_usuario),
                'credito_modo': 'cuotas',
                'credito_plan': {
                    'cantidad_cuotas': 4,
                    'frecuencia_dias': 30,
                    'fecha_primer_vencimiento': (date.today() + timedelta(days=30)).isoformat(),
                    'tasa_interes_pct': 10,
                },
                'client_request_id': 'ticket-credito-preview-001',
            },
        )
        assert response.status_code == 200
        venta_id = int((response.get_json() or {})['id_venta'])

        ticket_html = client.get(f'/ventas/{venta_id}/ticket?preview=1').get_data(as_text=True)
        assert 'Cobrado ahora' in ticket_html
        assert 'Saldo financiado' in ticket_html
        assert 'Detalle de pago' in ticket_html
        assert 'Efectivo' in ticket_html
        assert 'Credito Tienda' in ticket_html
        assert 'Interes total (10%)' in ticket_html
        assert 'Total en cuotas' in ticket_html
        assert 'Cantidad de cuotas' in ticket_html
        assert '>4<' in ticket_html
        assert 'Cuota estimada' in ticket_html


def test_ticket_contado_no_muestra_resumen_financiado():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    with app.app_context():
        admin = _login_admin(client)
        _abrir_caja(admin)

        cliente = Cliente(
            nombre='Cliente Ticket Contado',
            ruc_ci='8000666-1',
            tipo='minorista',
            activo=True,
        )
        db.session.add(cliente)
        db.session.commit()

        producto = _crear_producto(45000, 'TEST-TICKET-CONT-001')
        metodo_efectivo = _metodo_por_nombre('efectivo')
        assert metodo_efectivo is not None

        response = client.post(
            '/ventas/procesar',
            json={
                'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
                'pagos': [{'id_metodo_pago': int(metodo_efectivo.id_metodo_pago), 'monto': 45000}],
                'id_cliente': int(cliente.id_cliente),
                'id_usuario_vendedor': int(admin.id_usuario),
                'client_request_id': 'ticket-contado-preview-001',
            },
        )
        assert response.status_code == 200
        venta_id = int((response.get_json() or {})['id_venta'])

        ticket_html = client.get(f'/ventas/{venta_id}/ticket?preview=1').get_data(as_text=True)
        assert 'Pagado' in ticket_html
        assert 'Saldo financiado' not in ticket_html
        assert 'Total en cuotas' not in ticket_html
