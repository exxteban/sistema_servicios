"""Fase 1 del plan de BI: adaptador de fidelizacion por telefono en el cobro de gastronomia (datos ficticios).

Cubre el cobro real del POS: el celular identifica la venta. Con ficha activa la asigna; sin ficha y con un
celular valido crea la ficha; con duplicados, ficha inactiva, factura o fidelizacion apagada no asigna ni crea.
"""
from app import create_app, db
from app.models import Cliente, ClienteFidelizacionMovimiento, Configuracion, Venta
from app.services.clientes_fidelizacion import CONFIG_FIDELIZACION_ACTIVA
from gastronomia.models import GastronomiaPedidoPago
from gastronomia.services.bi.identidad import telefono_normalizado
from gastronomia.services.fidelizacion_telefono import cliente_por_telefono, resolver_cliente_fidelizacion
from test_gastronomia_caja import _abrir_caja, _crear_producto, _csrf, _loguear


def _activar_fidelizacion(app, activa: bool) -> str:
    with app.app_context():
        anterior = Configuracion.obtener(CONFIG_FIDELIZACION_ACTIVA, '') or ''
        Configuracion.establecer(CONFIG_FIDELIZACION_ACTIVA, '1' if activa else '0')
    return anterior


def _restaurar_fidelizacion(app, anterior: str) -> None:
    with app.app_context():
        Configuracion.establecer(CONFIG_FIDELIZACION_ACTIVA, anterior)


def _cliente(app, nombre: str, telefono: str, activo: bool = True) -> int:
    with app.app_context():
        cliente = Cliente(nombre=nombre, telefono=telefono, tipo='minorista', activo=activo)
        db.session.add(cliente)
        db.session.commit()
        return cliente.id_cliente


def _fichas_del_telefono(app, celular: str) -> list[dict]:
    """Fichas con ese celular normalizado, leidas dentro del contexto para no depender de sesiones abiertas."""
    with app.app_context():
        objetivo = telefono_normalizado(celular)
        return [
            {'id': c.id_cliente, 'nombre': c.nombre, 'telefono': c.telefono, 'activo': bool(c.activo), 'tipo': c.tipo}
            for c in Cliente.query.all()
            if telefono_normalizado(c.telefono) == objetivo
        ]


def _cantidad_clientes(app) -> int:
    with app.app_context():
        return Cliente.query.count()


def _pedido_listo(client, csrf: str, producto_id: int, celular: str, nombre: str | None = None) -> int:
    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mostrador',
            'referencia_entrega': 'Fidelidad',
            'nombre_cliente': nombre or '',
            'celular_cliente': celular,
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        },
        headers={'X-CSRFToken': csrf},
    )
    assert pedido_resp.status_code == 201
    pedido_id = pedido_resp.get_json()['pedido']['id_pedido']
    estado_resp = client.post(
        f'/api/gastronomia/pedidos/{pedido_id}/estado',
        json={'estado': 'listo'},
        headers={'X-CSRFToken': csrf},
    )
    assert estado_resp.status_code == 200
    return pedido_id


def _cobrar(client, csrf: str, pedido_id: int, extra: dict | None = None):
    respuesta = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo', **(extra or {})},
        headers={'X-CSRFToken': csrf},
    )
    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)


def _id_cliente_de_la_venta(app, pedido_id: int) -> int:
    with app.app_context():
        pago = GastronomiaPedidoPago.query.filter_by(pedido_id=pedido_id).first()
        assert pago is not None and pago.id_venta is not None
        return int(db.session.get(Venta, pago.id_venta).id_cliente)


def _compras_acumuladas(app, cliente_id: int) -> int:
    with app.app_context():
        return int(db.session.get(Cliente, cliente_id).fidelizacion_compras_acumuladas or 0)


def _escenario_cobro(username: str):
    app = create_app('testing')
    client = app.test_client()
    _, producto_id = _crear_producto(app, f'Fidelidad {username}', username)
    _loguear(client, app, username)
    _abrir_caja(app, username)
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    return app, client, producto_id, csrf


def test_cobro_con_ficha_activa_asigna_la_venta_y_suma_la_compra():
    app, client, producto_id, csrf = _escenario_cobro('fide_cobro_suma')
    cliente_id = _cliente(app, 'Ana Fidelidad', '0981 730 001')
    anterior = _activar_fidelizacion(app, True)
    try:
        pedido_id = _pedido_listo(client, csrf, producto_id, '0981730001')
        _cobrar(client, csrf, pedido_id)
        assert _id_cliente_de_la_venta(app, pedido_id) == cliente_id
        assert _compras_acumuladas(app, cliente_id) == 1
        with app.app_context():
            movimientos = ClienteFidelizacionMovimiento.query.filter_by(
                id_cliente=cliente_id, tipo_movimiento='compra_venta',
            ).count()
        assert movimientos == 1
        assert len(_fichas_del_telefono(app, '0981730001')) == 1
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_cobro_sin_ficha_crea_el_cliente_con_el_nombre_del_pedido():
    app, client, producto_id, csrf = _escenario_cobro('fide_crea_ficha')
    anterior = _activar_fidelizacion(app, True)
    try:
        pedido_id = _pedido_listo(client, csrf, producto_id, '0981 740 001', nombre='Lola Nueva')
        _cobrar(client, csrf, pedido_id)
        fichas = _fichas_del_telefono(app, '0981 740 001')
        assert len(fichas) == 1
        assert fichas[0]['nombre'] == 'Lola Nueva'
        assert fichas[0]['telefono'] == '+595981740001'
        assert fichas[0]['activo'] is True and fichas[0]['tipo'] == 'minorista'
        assert _id_cliente_de_la_venta(app, pedido_id) == fichas[0]['id']
        assert _compras_acumuladas(app, fichas[0]['id']) == 1
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_segunda_compra_con_otro_formato_reusa_la_ficha_creada():
    app, client, producto_id, csrf = _escenario_cobro('fide_reusa_ficha')
    anterior = _activar_fidelizacion(app, True)
    try:
        primera = _pedido_listo(client, csrf, producto_id, '0981 741 001', nombre='Mili')
        _cobrar(client, csrf, primera)
        segunda = _pedido_listo(client, csrf, producto_id, '+595 981 741 001')
        _cobrar(client, csrf, segunda)
        fichas = _fichas_del_telefono(app, '0981 741 001')
        assert len(fichas) == 1
        assert _id_cliente_de_la_venta(app, segunda) == fichas[0]['id']
        assert _compras_acumuladas(app, fichas[0]['id']) == 2
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_anular_la_venta_revierte_la_compra_sumada_por_telefono():
    app, client, producto_id, csrf = _escenario_cobro('fide_anula')
    cliente_id = _cliente(app, 'Gaby Anula', '0981 790 001')
    anterior = _activar_fidelizacion(app, True)
    try:
        pedido_id = _pedido_listo(client, csrf, producto_id, '0981790001')
        _cobrar(client, csrf, pedido_id)
        assert _compras_acumuladas(app, cliente_id) == 1
        anulacion = client.post(
            f'/api/gastronomia/reportes/pedidos/{pedido_id}/anular-venta',
            json={'motivo': 'Error de carga'},
            headers={'X-CSRFToken': csrf},
        )
        assert anulacion.status_code == 200
        assert _compras_acumuladas(app, cliente_id) == 0
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_cliente_elegido_para_la_factura_tiene_prioridad_sobre_el_telefono():
    app, client, producto_id, csrf = _escenario_cobro('fide_factura_manda')
    cliente_telefono = _cliente(app, 'Bea Telefono', '0981 750 001')
    cliente_factura = _cliente(app, 'Empresa Factura', '0981 750 999')
    anterior = _activar_fidelizacion(app, True)
    try:
        pedido_id = _pedido_listo(client, csrf, producto_id, '0981750001')
        _cobrar(client, csrf, pedido_id, {'id_cliente_factura': cliente_factura})
        assert _id_cliente_de_la_venta(app, pedido_id) == cliente_factura
        assert _compras_acumuladas(app, cliente_telefono) == 0
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_sin_fidelizacion_activa_no_asigna_ni_crea_fichas():
    app, client, producto_id, csrf = _escenario_cobro('fide_apagada')
    cliente_id = _cliente(app, 'Carla Apagada', '0981 760 001')
    anterior = _activar_fidelizacion(app, False)
    clientes_antes = _cantidad_clientes(app)
    try:
        pedido_id = _pedido_listo(client, csrf, producto_id, '0981760001')
        _cobrar(client, csrf, pedido_id)
        assert _id_cliente_de_la_venta(app, pedido_id) == 1
        assert _compras_acumuladas(app, cliente_id) == 0
        pedido_nuevo = _pedido_listo(client, csrf, producto_id, '0981 761 001', nombre='Sin fidelizacion')
        _cobrar(client, csrf, pedido_nuevo)
        assert _id_cliente_de_la_venta(app, pedido_nuevo) == 1
        assert _fichas_del_telefono(app, '0981 761 001') == []
        assert _cantidad_clientes(app) == clientes_antes
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_telefono_compartido_por_dos_fichas_no_asigna_ni_crea():
    app, client, producto_id, csrf = _escenario_cobro('fide_homonimos')
    primero = _cliente(app, 'Dani Uno', '0981 770 001')
    segundo = _cliente(app, 'Dani Dos', '0981 770 001')
    anterior = _activar_fidelizacion(app, True)
    clientes_antes = _cantidad_clientes(app)
    try:
        pedido_id = _pedido_listo(client, csrf, producto_id, '0981770001', nombre='Dani Tercero')
        _cobrar(client, csrf, pedido_id)
        assert _id_cliente_de_la_venta(app, pedido_id) == 1
        assert _compras_acumuladas(app, primero) == 0
        assert _compras_acumuladas(app, segundo) == 0
        assert _cantidad_clientes(app) == clientes_antes
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_ficha_inactiva_con_el_mismo_telefono_evita_crear_un_duplicado():
    app, client, producto_id, csrf = _escenario_cobro('fide_inactiva')
    inactiva = _cliente(app, 'Fer Inactiva', '0981 745 001', activo=False)
    anterior = _activar_fidelizacion(app, True)
    clientes_antes = _cantidad_clientes(app)
    try:
        pedido_id = _pedido_listo(client, csrf, producto_id, '0981745001', nombre='Fer')
        _cobrar(client, csrf, pedido_id)
        assert _id_cliente_de_la_venta(app, pedido_id) == 1
        assert _compras_acumuladas(app, inactiva) == 0
        assert _cantidad_clientes(app) == clientes_antes
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_busqueda_y_creacion_normalizan_el_telefono_y_respetan_las_reglas():
    app = create_app('testing')
    _cliente(app, 'Eli Formato', '0981 780 001')
    _cliente(app, 'Eli Inactivo', '0981 780 002', activo=False)
    anterior = _activar_fidelizacion(app, True)
    try:
        with app.app_context():
            encontrado = cliente_por_telefono('+595 981 780 001')
            assert encontrado is not None and encontrado.nombre == 'Eli Formato'
            assert cliente_por_telefono('0981 780 002') is None
            assert cliente_por_telefono('') is None
            assert cliente_por_telefono(None) is None
        clientes_antes = _cantidad_clientes(app)
        with app.app_context():
            assert resolver_cliente_fidelizacion('0981 780 001', 'Otra', True) is None
            assert resolver_cliente_fidelizacion('0981 780 002', 'Otra', False) is None
            assert resolver_cliente_fidelizacion('12', 'Otra', False) is None
            assert resolver_cliente_fidelizacion(None, 'Otra', False) is None
            db.session.rollback()
        assert _cantidad_clientes(app) == clientes_antes
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_factura_electronica_no_asigna_ni_crea_fichas():
    app = create_app('testing')
    anterior = _activar_fidelizacion(app, True)
    clientes_antes = _cantidad_clientes(app)
    try:
        with app.app_context():
            assert resolver_cliente_fidelizacion('0981 782 001', 'Factura', True) is None
            db.session.rollback()
        assert _cantidad_clientes(app) == clientes_antes
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_pos_muestra_la_frase_de_fidelizacion_solo_si_esta_activa():
    app, client, _producto_id, _csrf_token = _escenario_cobro('fide_pos_texto')
    frase = 'cada compra suma para la fidelización'
    anterior = _activar_fidelizacion(app, True)
    try:
        assert frase in client.get('/gastronomia/pos').get_data(as_text=True)
        _activar_fidelizacion(app, False)
        assert frase not in client.get('/gastronomia/pos').get_data(as_text=True)
    finally:
        _restaurar_fidelizacion(app, anterior)
