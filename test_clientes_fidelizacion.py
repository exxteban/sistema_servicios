from datetime import date, datetime, timedelta
from uuid import uuid4

from app import create_app, db
from app.models import Caja, Cliente, ClienteFidelizacionMovimiento, Configuracion, SesionCaja, Usuario, Venta
from app.routes.ventas.ticket_context import build_sales_ticket_context
from app.services.clientes_fidelizacion import (
    CONFIG_FIDELIZACION_ACTIVA,
    CONFIG_FIDELIZACION_BENEFICIO_DESCRIPCION,
    CONFIG_FIDELIZACION_BENEFICIO_TIPO,
    CONFIG_FIDELIZACION_BENEFICIO_VALOR,
    CONFIG_FIDELIZACION_COMPRAS_REQUERIDAS,
    CONFIG_FIDELIZACION_PREMIOS_POR_OBJETIVO,
    canjear_beneficios_cliente,
    guardar_fidelizacion_config,
    obtener_beneficios_pos_cliente,
    obtener_resumen_beneficios_cliente,
    registrar_canje_beneficio_en_venta,
    registrar_compra_fidelizacion_por_venta,
    resolver_descuento_beneficio_pos,
    revertir_fidelizacion_por_anulacion_venta,
)
from app.services.clientes_fidelizacion_support import (
    CONFIG_FIDELIZACION_BENEFICIO_VIGENCIA_DIAS,
    CONFIG_FIDELIZACION_COMPRAS_VENTANA_DIAS,
)
from app.services.clientes_fidelizacion_politica import (
    CONFIG_FIDELIZACION_MAX_BENEFICIOS_ACTIVOS,
    CONFIG_FIDELIZACION_MAX_BENEFICIOS_VENTANA,
    CONFIG_FIDELIZACION_MODO_GENERACION,
    MODO_UNA_VEZ_VENTANA,
)
from app.services.clientes_fidelizacion_sincronizacion import sincronizar_compras_fidelizacion_pendientes


def _crear_sesion_prueba():
    admin = Usuario.query.filter_by(username='admin').first()
    caja = Caja.query.first()
    sesion = SesionCaja(id_caja=caja.id_caja, id_usuario=admin.id_usuario, monto_inicial=0, estado='cerrada')
    db.session.add(sesion)
    db.session.flush()
    return admin, sesion


def _crear_cliente_prueba():
    suffix = uuid4().hex[:8]
    cliente = Cliente(nombre=f'Cliente Fidelizacion {suffix}', tipo='minorista', activo=True)
    db.session.add(cliente)
    db.session.flush()
    return cliente


def _crear_venta(cliente, sesion, total=100000, fecha_venta=None):
    venta = Venta(
        id_cliente=cliente.id_cliente,
        id_sesion_caja=sesion.id_sesion,
        subtotal=total,
        total=total,
        estado='completada',
    )
    if fecha_venta is not None:
        venta.fecha_venta = fecha_venta
    db.session.add(venta)
    db.session.flush()
    return venta


def _configurar_fidelizacion(*, tipo='descuento_porcentaje', valor='10', descripcion='Promo fidelidad', vigencia_dias='30', ventana_dias='365', compras_requeridas='3', premios_por_objetivo='2', modo_generacion='acumulativo', max_activos='0', max_ventana='0'):
    Configuracion.establecer(CONFIG_FIDELIZACION_ACTIVA, '1', 'test fidelizacion activa')
    Configuracion.establecer(CONFIG_FIDELIZACION_COMPRAS_REQUERIDAS, compras_requeridas, 'test compras requeridas')
    Configuracion.establecer(CONFIG_FIDELIZACION_PREMIOS_POR_OBJETIVO, premios_por_objetivo, 'test premios por objetivo')
    Configuracion.establecer(CONFIG_FIDELIZACION_COMPRAS_VENTANA_DIAS, ventana_dias, 'test ventana compras')
    Configuracion.establecer(CONFIG_FIDELIZACION_MODO_GENERACION, modo_generacion, 'test modo generacion')
    Configuracion.establecer(CONFIG_FIDELIZACION_MAX_BENEFICIOS_ACTIVOS, max_activos, 'test max activos')
    Configuracion.establecer(CONFIG_FIDELIZACION_MAX_BENEFICIOS_VENTANA, max_ventana, 'test max ventana')
    Configuracion.establecer(CONFIG_FIDELIZACION_BENEFICIO_TIPO, tipo, 'test tipo beneficio')
    Configuracion.establecer(CONFIG_FIDELIZACION_BENEFICIO_VALOR, valor, 'test valor beneficio')
    Configuracion.establecer(CONFIG_FIDELIZACION_BENEFICIO_VIGENCIA_DIAS, vigencia_dias, 'test vigencia beneficio')
    Configuracion.establecer(CONFIG_FIDELIZACION_BENEFICIO_DESCRIPCION, descripcion, 'test descripcion beneficio')


def test_fidelizacion_libera_beneficios_al_llegar_al_objetivo():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion(tipo='descuento_porcentaje', valor='10', descripcion='Descuento VIP')
        admin, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()

        resultados = []
        for _ in range(3):
            venta = _crear_venta(cliente, sesion)
            resultados.append(registrar_compra_fidelizacion_por_venta(venta, id_usuario=admin.id_usuario))
        db.session.commit()
        cliente = db.session.get(Cliente, cliente.id_cliente)
        resumen = obtener_resumen_beneficios_cliente(cliente.id_cliente)

        assert resultados[-1]['beneficios_generados'] == 2
        assert cliente.fidelizacion_compras_acumuladas_seguras == 0
        assert cliente.fidelizacion_consumos_disponibles_seguro == 2
        assert cliente.fidelizacion_consumos_canjeados_seguro == 0
        assert resumen['items'][0]['cantidad'] == 2
        assert '10% de descuento' in resumen['items'][0]['resumen']


def test_fidelizacion_no_duplica_venta_reprocesada():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion()
        admin, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()
        venta = _crear_venta(cliente, sesion)

        registrar_compra_fidelizacion_por_venta(venta, id_usuario=admin.id_usuario)
        registrar_compra_fidelizacion_por_venta(venta, id_usuario=admin.id_usuario)
        db.session.commit()
        cliente = db.session.get(Cliente, cliente.id_cliente)

        assert cliente.fidelizacion_compras_acumuladas_seguras == 1
        assert cliente.fidelizacion_consumos_disponibles_seguro == 0


def test_fidelizacion_respeta_tipo_ganado_antes_de_cambiar_configuracion():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion(tipo='descuento_porcentaje', valor='10', descripcion='Descuento inicial')
        admin, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()

        for _ in range(3):
            venta = _crear_venta(cliente, sesion)
            registrar_compra_fidelizacion_por_venta(venta, id_usuario=admin.id_usuario)
        db.session.commit()

        _configurar_fidelizacion(tipo='saldo_favor', valor='50000', descripcion='Credito tienda')
        resumen = obtener_resumen_beneficios_cliente(cliente.id_cliente)

        assert resumen['items'][0]['cantidad'] == 2
        assert '10% de descuento' in resumen['items'][0]['resumen']


def test_fidelizacion_permite_canje_y_revierte_beneficio_por_anulacion():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion(tipo='descuento_monto', valor='50000', descripcion='Vale de compra')
        admin, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()
        ventas = []
        for _ in range(3):
            venta = _crear_venta(cliente, sesion)
            ventas.append(venta)
            registrar_compra_fidelizacion_por_venta(venta, id_usuario=admin.id_usuario)
        db.session.commit()

        resultado_canje = canjear_beneficios_cliente(
            cliente.id_cliente,
            1,
            id_usuario=admin.id_usuario,
            descripcion='Canje de prueba',
        )
        db.session.commit()
        revertir_fidelizacion_por_anulacion_venta(ventas[-1], id_usuario=admin.id_usuario)
        db.session.commit()
        cliente = db.session.get(Cliente, cliente.id_cliente)

        assert resultado_canje['beneficios_canjeados'] == 1
        assert 'Gs. 50.000 de descuento' in resultado_canje['beneficios_canjeados_resumen'][0]['resumen']
        assert cliente.fidelizacion_compras_acumuladas_seguras == 2
        assert cliente.fidelizacion_consumos_disponibles_seguro == -1
        assert cliente.fidelizacion_consumos_canjeados_seguro == 1


def test_fidelizacion_resuelve_y_aplica_beneficio_opcional_en_pos():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion(tipo='descuento_porcentaje', valor='20', descripcion='Promo POS')
        admin, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()
        ventas = []
        for _ in range(3):
            venta = _crear_venta(cliente, sesion, total=120000)
            ventas.append(venta)
            registrar_compra_fidelizacion_por_venta(venta, id_usuario=admin.id_usuario)
        db.session.commit()

        beneficios_pos = obtener_beneficios_pos_cliente(cliente.id_cliente)
        beneficio_id = beneficios_pos['items'][0]['id_movimiento']
        resolucion = resolver_descuento_beneficio_pos(cliente.id_cliente, beneficio_id, subtotal=200000, descuento_manual=10000)
        assert float(resolucion['descuento_adicional']) == 38000.0

        venta_aplicacion = _crear_venta(cliente, sesion, total=152000)
        snapshot = registrar_canje_beneficio_en_venta(
            cliente.id_cliente,
            beneficio_id,
            venta_aplicacion.id_venta,
            id_usuario=admin.id_usuario,
        )
        db.session.commit()
        cliente = db.session.get(Cliente, cliente.id_cliente)
        resumen = obtener_resumen_beneficios_cliente(cliente.id_cliente)

        assert snapshot['tipo'] == 'descuento_porcentaje'
        assert cliente.fidelizacion_consumos_disponibles_seguro == 1
        assert cliente.fidelizacion_consumos_canjeados_seguro == 1
        assert resumen['cantidad'] == 1
        assert '20% de descuento' in resumen['items'][0]['resumen']

        revertir_fidelizacion_por_anulacion_venta(venta_aplicacion, id_usuario=admin.id_usuario)
        db.session.commit()
        cliente = db.session.get(Cliente, cliente.id_cliente)

        assert cliente.fidelizacion_consumos_disponibles_seguro == 2
        assert cliente.fidelizacion_consumos_canjeados_seguro == 0


def test_ticket_context_expone_beneficio_aplicado_en_venta():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion(tipo='saldo_favor', valor='40000', descripcion='Saldo cliente fiel')
        admin, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()
        for _ in range(3):
            venta = _crear_venta(cliente, sesion, total=100000)
            registrar_compra_fidelizacion_por_venta(venta, id_usuario=admin.id_usuario)
        db.session.commit()

        beneficio_id = obtener_beneficios_pos_cliente(cliente.id_cliente)['items'][0]['id_movimiento']
        venta_aplicacion = _crear_venta(cliente, sesion, total=60000)
        registrar_canje_beneficio_en_venta(
            cliente.id_cliente,
            beneficio_id,
            venta_aplicacion.id_venta,
            id_usuario=admin.id_usuario,
        )
        db.session.commit()

        ctx = build_sales_ticket_context(
            venta_aplicacion,
            detalles=[],
            pagos=[],
            pagos_resumen=[],
            preview=True,
            embedded=False,
        )

        assert 'saldo a favor' in ctx['beneficio_aplicado_texto'].lower()
        assert ctx['beneficios_aplicados'][0]['resumen']


def test_fidelizacion_descarta_beneficios_vencidos():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion(tipo='descuento_porcentaje', valor='15', descripcion='Promo breve', vigencia_dias='1')
        admin, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()

        for _ in range(3):
            venta = _crear_venta(cliente, sesion, total=90000)
            registrar_compra_fidelizacion_por_venta(venta, id_usuario=admin.id_usuario)
        db.session.commit()

        beneficios = ClienteFidelizacionMovimiento.query.filter_by(
            id_cliente=cliente.id_cliente,
            tipo_movimiento='beneficio_otorgado',
        ).all()
        for beneficio in beneficios:
            beneficio.beneficio_fecha_vencimiento = date.today() - timedelta(days=1)
        db.session.commit()

        resumen = obtener_resumen_beneficios_cliente(cliente.id_cliente)
        beneficios_pos = obtener_beneficios_pos_cliente(cliente.id_cliente)
        db.session.commit()
        cliente = db.session.get(Cliente, cliente.id_cliente)

        assert resumen['cantidad'] == 0
        assert beneficios_pos['cantidad'] == 0
        assert cliente.fidelizacion_consumos_disponibles_seguro == 0
        assert ClienteFidelizacionMovimiento.query.filter_by(
            id_cliente=cliente.id_cliente,
            tipo_movimiento='beneficio_vencido',
        ).count() == 2


def test_guardar_configuracion_actualiza_beneficios_activos_a_tipo_pos():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion(
            tipo='consumo_libre',
            valor='0',
            descripcion='Servicio libre',
            compras_requeridas='3',
            premios_por_objetivo='1',
        )
        admin, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()

        for _ in range(3):
            venta = _crear_venta(cliente, sesion, total=120000)
            registrar_compra_fidelizacion_por_venta(venta, id_usuario=admin.id_usuario)
        db.session.commit()

        beneficios_antes = obtener_beneficios_pos_cliente(cliente.id_cliente)
        assert beneficios_antes['cantidad'] == 1
        assert beneficios_antes['items'][0]['pos_aplicable'] is False

        guardar_fidelizacion_config(
            True,
            3,
            1,
            365,
            'acumulativo',
            0,
            0,
            'descuento_monto',
            '100000',
            30,
            'Promo actualizada',
        )

        beneficios_despues = obtener_beneficios_pos_cliente(cliente.id_cliente)
        resolucion = resolver_descuento_beneficio_pos(
            cliente.id_cliente,
            beneficios_despues['items'][0]['id_movimiento'],
            subtotal=150000,
            descuento_manual=0,
        )

        assert beneficios_despues['cantidad'] == 1
        assert beneficios_despues['items'][0]['pos_aplicable'] is True
        assert beneficios_despues['items'][0]['tipo'] == 'descuento_monto'
        assert beneficios_despues['items'][0]['descripcion'] == 'Promo actualizada'
        assert float(resolucion['descuento_adicional']) == 100000.0


def test_fidelizacion_sincroniza_compras_historicas_dentro_de_ventana():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion(
            tipo='descuento_porcentaje',
            valor='10',
            descripcion='Historico valido',
            vigencia_dias='900',
            ventana_dias='900',
            compras_requeridas='2',
            premios_por_objetivo='1',
        )
        _, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()

        for i in range(7):
            _crear_venta(
                cliente,
                sesion,
                total=100000,
                fecha_venta=datetime.utcnow() - timedelta(days=10 + i),
            )
        db.session.commit()

        procesadas = sincronizar_compras_fidelizacion_pendientes(id_cliente=cliente.id_cliente)
        db.session.commit()
        cliente = db.session.get(Cliente, cliente.id_cliente)
        resumen = obtener_resumen_beneficios_cliente(cliente.id_cliente)

        assert procesadas == 7
        assert cliente.fidelizacion_compras_acumuladas_seguras == 1
        assert cliente.fidelizacion_consumos_disponibles_seguro == 3
        assert resumen['cantidad'] == 3
        assert sincronizar_compras_fidelizacion_pendientes(id_cliente=cliente.id_cliente) == 0


def test_fidelizacion_no_sincroniza_compras_historicas_fuera_de_ventana():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion(ventana_dias='5')
        _, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()

        for i in range(3):
            _crear_venta(
                cliente,
                sesion,
                total=100000,
                fecha_venta=datetime.utcnow() - timedelta(days=30 + i),
            )
        db.session.commit()

        assert sincronizar_compras_fidelizacion_pendientes(id_cliente=cliente.id_cliente) == 0
        resumen = obtener_resumen_beneficios_cliente(cliente.id_cliente)

        assert resumen['cantidad'] == 0
        assert db.session.get(Cliente, cliente.id_cliente).fidelizacion_compras_acumuladas_seguras == 0


def test_fidelizacion_modo_una_vez_por_ventana_limita_beneficios():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion(
            compras_requeridas='2',
            premios_por_objetivo='1',
            ventana_dias='900',
            modo_generacion=MODO_UNA_VEZ_VENTANA,
        )
        _, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()

        for _ in range(7):
            venta = _crear_venta(cliente, sesion, total=100000)
            registrar_compra_fidelizacion_por_venta(venta)
        db.session.commit()
        cliente = db.session.get(Cliente, cliente.id_cliente)
        resumen = obtener_resumen_beneficios_cliente(cliente.id_cliente)

        assert resumen['cantidad'] == 1
        assert cliente.fidelizacion_consumos_disponibles_seguro == 1


def test_fidelizacion_respeta_tope_activo_por_cliente():
    app = create_app('testing')

    with app.app_context():
        _configurar_fidelizacion(
            compras_requeridas='2',
            premios_por_objetivo='1',
            max_activos='2',
        )
        _, sesion = _crear_sesion_prueba()
        cliente = _crear_cliente_prueba()

        for _ in range(8):
            venta = _crear_venta(cliente, sesion, total=100000)
            registrar_compra_fidelizacion_por_venta(venta)
        db.session.commit()
        cliente = db.session.get(Cliente, cliente.id_cliente)

        assert obtener_resumen_beneficios_cliente(cliente.id_cliente)['cantidad'] == 2
        assert cliente.fidelizacion_compras_acumuladas_seguras == 4
