"""Fase 1 del plan de BI: ficha por telefono y beneficios de fidelizacion en el cobro de gastronomia (datos ficticios).

Cubre el cobro real de la caja: el celular identifica la venta (ficha existente o nueva), la factura puede
completar el RUC de esa ficha, y un beneficio elegido se descuenta y se devuelve si la venta se anula.
"""
from unittest.mock import patch

from app import create_app, db
from app.models import Cliente, ClienteFidelizacionMovimiento, Configuracion, Usuario, Venta
from app.services.clientes_fidelizacion import (
    CONFIG_FIDELIZACION_ACTIVA,
    CONFIG_FIDELIZACION_BENEFICIO_TIPO,
    CONFIG_FIDELIZACION_BENEFICIO_VALOR,
    CONFIG_FIDELIZACION_COMPRAS_REQUERIDAS,
    CONFIG_FIDELIZACION_PREMIOS_POR_OBJETIVO,
    obtener_beneficios_pos_cliente,
)
from gastronomia.bi_models import GastronomiaBiFichaTelefono
from gastronomia.models import GastronomiaPedidoPago
from gastronomia.services.bi.identidad import telefono_normalizado
from gastronomia.services.fidelizacion_telefono import (
    MSG_CARRERA,
    cliente_por_telefono,
    resolver_cliente_fidelizacion,
)
from test_gastronomia_caja import _abrir_caja, _crear_producto, _csrf, _loguear

CONFIG_BENEFICIO = {
    CONFIG_FIDELIZACION_COMPRAS_REQUERIDAS: '1',
    CONFIG_FIDELIZACION_PREMIOS_POR_OBJETIVO: '1',
    CONFIG_FIDELIZACION_BENEFICIO_TIPO: 'descuento_porcentaje',
    CONFIG_FIDELIZACION_BENEFICIO_VALOR: '10',
}


def _activar_fidelizacion(app, activa: bool) -> str:
    with app.app_context():
        anterior = Configuracion.obtener(CONFIG_FIDELIZACION_ACTIVA, '') or ''
        Configuracion.establecer(CONFIG_FIDELIZACION_ACTIVA, '1' if activa else '0')
    return anterior


def _restaurar_fidelizacion(app, anterior: str) -> None:
    with app.app_context():
        Configuracion.establecer(CONFIG_FIDELIZACION_ACTIVA, anterior)


def _configurar_beneficio(app) -> dict:
    anteriores = {}
    with app.app_context():
        for clave, valor in CONFIG_BENEFICIO.items():
            anteriores[clave] = Configuracion.obtener(clave, '') or ''
            Configuracion.establecer(clave, valor)
    return anteriores


def _restaurar_configuracion(app, anteriores: dict) -> None:
    with app.app_context():
        for clave, valor in anteriores.items():
            Configuracion.establecer(clave, valor)


def _cliente(app, nombre: str, telefono: str, activo: bool = True) -> int:
    with app.app_context():
        cliente = Cliente(nombre=nombre, telefono=telefono, tipo='minorista', activo=activo)
        db.session.add(cliente)
        db.session.commit()
        return cliente.id_cliente


def _negocio_id(app, username: str) -> int:
    with app.app_context():
        return int(Usuario.query.filter_by(username=username).first().id_cliente)


def _fichas_del_telefono(app, celular: str) -> list[dict]:
    """Fichas con ese celular normalizado, leidas dentro del contexto."""
    with app.app_context():
        objetivo = telefono_normalizado(celular)
        return [
            {'id': c.id_cliente, 'nombre': c.nombre, 'telefono': c.telefono, 'activo': bool(c.activo),
             'tipo': c.tipo, 'ruc_ci': c.ruc_ci}
            for c in Cliente.query.all()
            if telefono_normalizado(c.telefono) == objetivo
        ]


def _cantidad_clientes(app) -> int:
    with app.app_context():
        return Cliente.query.count()


def _pedido_listo(client, csrf: str, producto_id: int, celular: str | None, nombre: str | None = None) -> int:
    pedido_resp = client.post(
        '/api/gastronomia/pedidos',
        json={
            'tipo_pedido': 'mostrador',
            'referencia_entrega': 'Fidelidad',
            'nombre_cliente': nombre or '',
            'celular_cliente': celular or '',
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
    return respuesta.get_json()


def _venta_del_pedido(app, pedido_id: int) -> Venta:
    with app.app_context():
        pago = GastronomiaPedidoPago.query.filter_by(pedido_id=pedido_id).first()
        assert pago is not None and pago.id_venta is not None
        venta = db.session.get(Venta, pago.id_venta)
        return venta


def _id_cliente_de_la_venta(app, pedido_id: int) -> int:
    return int(_venta_del_pedido(app, pedido_id).id_cliente)


def _compras_acumuladas(app, cliente_id: int) -> int:
    with app.app_context():
        return int(db.session.get(Cliente, cliente_id).fidelizacion_compras_acumuladas or 0)


def _beneficios_disponibles(app, cliente_id: int) -> list[int]:
    with app.app_context():
        return [item['id_movimiento'] for item in obtener_beneficios_pos_cliente(cliente_id)['items']]


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


def test_dos_cobros_que_crean_la_misma_ficha_no_dejan_dos_fichas():
    app, client, producto_id, csrf = _escenario_cobro('fide_carrera')
    negocio = _negocio_id(app, 'fide_carrera')
    # Otro cobro ya guardo la ficha de este celular, pero este cobro todavia no la ve.
    ficha_otro_cobro = _cliente(app, 'Otro cobro', '0981 785 001')
    with app.app_context():
        db.session.add(GastronomiaBiFichaTelefono(
            cliente_id=negocio, telefono_normalizado='+595981785001', id_cliente_ficha=ficha_otro_cobro,
        ))
        db.session.commit()
    anterior = _activar_fidelizacion(app, True)
    clientes_antes = _cantidad_clientes(app)
    try:
        with app.app_context(), \
                patch('gastronomia.services.fidelizacion_telefono._ficha_registrada', return_value=None), \
                patch('gastronomia.services.fidelizacion_telefono._clientes_con_telefono', return_value=[]):
            try:
                resolver_cliente_fidelizacion(negocio, '0981 785 001', 'Segundo cobro', False)
                raise AssertionError('Debia rechazar la segunda ficha')
            except ValueError as error:
                assert str(error) == MSG_CARRERA
        assert _cantidad_clientes(app) == clientes_antes
        assert len(_fichas_del_telefono(app, '0981 785 001')) == 1
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_la_ficha_registrada_se_reutiliza_sin_crear_otra():
    app = create_app('testing')
    _crear_producto(app, 'Fidelidad reutiliza', 'fide_reutiliza')
    negocio = _negocio_id(app, 'fide_reutiliza')
    ficha = _cliente(app, 'Ya registrada', '0981 786 001')
    with app.app_context():
        db.session.add(GastronomiaBiFichaTelefono(
            cliente_id=negocio, telefono_normalizado='+595981786001', id_cliente_ficha=ficha,
        ))
        db.session.commit()
    anterior = _activar_fidelizacion(app, True)
    clientes_antes = _cantidad_clientes(app)
    try:
        with app.app_context():
            encontrado = resolver_cliente_fidelizacion(negocio, '0981 786 001', 'Otro nombre', False)
            assert encontrado is not None and encontrado.id_cliente == ficha
        assert _cantidad_clientes(app) == clientes_antes
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_factura_completa_el_ruc_de_la_ficha_del_pedido_sin_duplicar():
    app, client, producto_id, csrf = _escenario_cobro('fide_ruc')
    anterior = _activar_fidelizacion(app, True)
    try:
        primera = _pedido_listo(client, csrf, producto_id, '0981 810 001', nombre='Nora')
        _cobrar(client, csrf, primera)
        ficha = _fichas_del_telefono(app, '0981 810 001')[0]
        abierto = _pedido_listo(client, csrf, producto_id, '0981 810 001')
        clientes_antes = _cantidad_clientes(app)
        respuesta = client.post(
            '/api/gastronomia/caja/clientes-factura',
            json={'nombre': 'Nora Factura SA', 'ruc_ci': '80123456-7', 'pedido_id': abierto},
            headers={'X-CSRFToken': csrf},
        )
        assert respuesta.status_code == 200, respuesta.get_data(as_text=True)
        assert respuesta.get_json()['cliente']['id_cliente'] == ficha['id']
        assert _cantidad_clientes(app) == clientes_antes
        completada = _fichas_del_telefono(app, '0981 810 001')[0]
        assert completada['ruc_ci'] == '80123456-7'
        assert completada['nombre'] == 'Nora'
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_alta_de_factura_sin_pedido_sigue_creando_un_cliente_nuevo():
    app, client, producto_id, csrf = _escenario_cobro('fide_alta_nueva')
    respuesta = client.post(
        '/api/gastronomia/caja/clientes-factura',
        json={'nombre': 'Cliente Nuevo', 'ruc_ci': '4455667-8'},
        headers={'X-CSRFToken': csrf},
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()['cliente']['nombre'] == 'Cliente Nuevo'


def test_beneficio_se_estima_antes_del_cobro_y_se_descuenta_al_cobrar():
    app, client, producto_id, csrf = _escenario_cobro('fide_canje')
    _cliente(app, 'Caro Canje', '0981 800 001')
    anteriores = _configurar_beneficio(app)
    anterior = _activar_fidelizacion(app, True)
    try:
        primera = _pedido_listo(client, csrf, producto_id, '0981800001')
        _cobrar(client, csrf, primera)  # la primera compra genera el beneficio
        segunda = _pedido_listo(client, csrf, producto_id, '0981800001')
        cliente_id = _id_cliente_de_la_venta(app, primera)
        disponibles = client.get(f'/api/gastronomia/caja/pedidos/{segunda}/beneficios?descuento_monto=0')
        assert disponibles.status_code == 200
        items = disponibles.get_json()['items']
        assert len(items) == 1
        assert items[0]['descuento_estimado'] == 3000
        id_beneficio = items[0]['id_movimiento']
        base = f'/api/gastronomia/caja/pedidos/{segunda}/beneficios'
        assert client.get(f'{base}?factura_electronica=1').get_json()['items'] == []
        assert client.get(f'{base}?id_cliente_factura=7').get_json()['items'] == []

        cobro = _cobrar(client, csrf, segunda, {'beneficio_fidelizacion_id': id_beneficio})
        assert cobro['pedido']['pago']['total_cobrado'] == 27000
        venta = _venta_del_pedido(app, segunda)
        assert float(venta.descuento_fidelizacion_monto) == 3000
        with app.app_context():
            canjes = ClienteFidelizacionMovimiento.query.filter_by(
                tipo_movimiento='canje_venta', referencia_tipo='venta', referencia_id=int(venta.id_venta),
            ).count()
        assert canjes == 1
        assert id_beneficio not in _beneficios_disponibles(app, cliente_id)

        anulacion = client.post(
            f'/api/gastronomia/reportes/pedidos/{segunda}/anular-venta',
            json={'motivo': 'Error de carga'},
            headers={'X-CSRFToken': csrf},
        )
        assert anulacion.status_code == 200
        assert id_beneficio in _beneficios_disponibles(app, cliente_id)
    finally:
        _restaurar_fidelizacion(app, anterior)
        _restaurar_configuracion(app, anteriores)


def test_beneficio_sin_cliente_registrado_se_rechaza_sin_cobrar():
    app, client, producto_id, csrf = _escenario_cobro('fide_sin_cliente_beneficio')
    anterior = _activar_fidelizacion(app, True)
    try:
        pedido_id = _pedido_listo(client, csrf, producto_id, None)
        respuesta = client.post(
            f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
            json={'metodo_pago': 'efectivo', 'beneficio_fidelizacion_id': 999},
            headers={'X-CSRFToken': csrf},
        )
        assert respuesta.status_code == 400
        assert 'cliente registrado' in respuesta.get_json()['mensaje']
        disponibles = client.get(f'/api/gastronomia/caja/pedidos/{pedido_id}/beneficios')
        assert disponibles.get_json()['items'] == []
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_busqueda_y_creacion_normalizan_el_telefono_y_respetan_las_reglas():
    app, _client, _producto_id, _csrf_token = _escenario_cobro('fide_busqueda')
    negocio = _negocio_id(app, 'fide_busqueda')
    _cliente(app, 'Eli Formato', '0981 780 001')
    _cliente(app, 'Eli Inactivo', '0981 780 002', activo=False)
    anterior = _activar_fidelizacion(app, True)
    try:
        with app.app_context():
            encontrado = cliente_por_telefono(negocio, '+595 981 780 001')
            assert encontrado is not None and encontrado.nombre == 'Eli Formato'
            assert cliente_por_telefono(negocio, '0981 780 002') is None
            assert cliente_por_telefono(negocio, '') is None
            assert cliente_por_telefono(negocio, None) is None
        clientes_antes = _cantidad_clientes(app)
        with app.app_context():
            assert resolver_cliente_fidelizacion(negocio, '0981 780 002', 'Otra', False) is None
            assert resolver_cliente_fidelizacion(negocio, '12', 'Otra', False) is None
            assert resolver_cliente_fidelizacion(negocio, None, 'Otra', False) is None
        assert _cantidad_clientes(app) == clientes_antes
    finally:
        _restaurar_fidelizacion(app, anterior)


def test_factura_electronica_no_asigna_ni_crea_fichas():
    app, _client, _producto_id, _csrf_token = _escenario_cobro('fide_factura_fe')
    negocio = _negocio_id(app, 'fide_factura_fe')
    anterior = _activar_fidelizacion(app, True)
    clientes_antes = _cantidad_clientes(app)
    try:
        with app.app_context():
            assert resolver_cliente_fidelizacion(negocio, '0981 782 001', 'Factura', True) is None
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
