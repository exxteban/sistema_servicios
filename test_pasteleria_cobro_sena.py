"""Fase 1 (paso 5) del plan de pasteleria: cobro del saldo de un encargo con sena."""
from datetime import timedelta

import pytest

from app import create_app, db
from app.models import PagoVenta, Producto, SesionCaja, Usuario, Venta
from app.utils.helpers import now_local
from gastronomia.encargo_models import ADELANTO_APLICADO, ADELANTO_DEVUELTO, ADELANTO_VIGENTE
from gastronomia.models import GastronomiaClienteConfig, GastronomiaPedido, GastronomiaPedidoPago
from gastronomia.services.adelanto_service import cancelar_encargo, registrar_adelanto
from gastronomia.services.anulacion_service import anular_venta_gastronomica
from gastronomia.services.caja_service import cobrar_pedido
from gastronomia.services.encargo_service import crear_encargo
from gastronomia.services.pedido_service import cambiar_estado_pedido
from gastronomia.services.stock_service import guardar_receta
from gastronomia.services.venta_integration_service import crear_cola_cobro_central_desde_pedido
from test_gastronomia_caja import _abrir_caja
from test_gastronomia_pedidos import _agregar_insumo, _crear_menu_para_pedidos


def _fecha():
    base = now_local().replace(tzinfo=None) + timedelta(days=3)
    return base.replace(hour=15, minute=0, second=0, microsecond=0)


def _local(app, nombre: str, username: str):
    cliente_id, producto_id, _ = _crear_menu_para_pedidos(app, nombre, username)
    with app.app_context():
        GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one().encargos_activo = True
        db.session.commit()
        usuario_id = Usuario.query.filter_by(username=username).first().id_usuario
    return cliente_id, usuario_id, producto_id, _abrir_caja(app, username)


def _encargo(cliente_id, usuario_id, producto_id):
    # 7 x 15.000 = 105.000
    return crear_encargo(cliente_id, usuario_id, {
        'nombre_cliente': 'Ana',
        'fecha_programada': _fecha(),
        'items': [{'producto_id': producto_id, 'cantidad': 7}],
    })


def _efectivo(sesion_id) -> float:
    db.session.expire_all()
    return float(db.session.get(SesionCaja, sesion_id).calcular_total_efectivo())


def test_cobrar_el_saldo_descuenta_la_sena_y_la_caja_suma_el_total():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Cobro Sena 1', 'cobro_sena_1')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 30000})
        assert _efectivo(sesion_id) == 30000

        cobrar_pedido(cliente_id, usuario_id, pedido.id_pedido, {'metodo_pago': 'efectivo'})

        pago = GastronomiaPedidoPago.query.filter_by(pedido_id=pedido.id_pedido).one()
        assert float(pago.subtotal) == 105000
        assert float(pago.descuento_monto) == 30000
        assert float(pago.total_cobrado) == 75000

        venta = db.session.get(Venta, pago.id_venta)
        assert float(venta.subtotal) == 105000
        assert float(venta.descuento_monto) == 30000
        assert float(venta.descuento_manual_monto) == 0  # la sena no contamina el descuento manual
        assert float(venta.total) == 75000
        assert 'Sena aplicada: 30000.00' in venta.observaciones
        assert [float(p.monto) for p in PagoVenta.query.filter_by(id_venta=venta.id_venta)] == [75000]

        adelanto = pedido.adelantos.one()
        assert adelanto.estado == ADELANTO_APLICADO
        assert adelanto.id_venta == venta.id_venta
        assert _efectivo(sesion_id) == 105000  # sena + saldo = total, sin contar dos veces


def test_cobro_con_descuento_manual_y_sena():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Cobro Sena 2', 'cobro_sena_2')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 30000})

        with pytest.raises(ValueError, match='descuento'):
            cobrar_pedido(cliente_id, usuario_id, pedido.id_pedido, {'descuento_monto': 80000})
        assert pedido.adelantos.one().estado == ADELANTO_VIGENTE

        cobrar_pedido(cliente_id, usuario_id, pedido.id_pedido, {'descuento_monto': 5000})
        venta = db.session.get(Venta, GastronomiaPedidoPago.query.filter_by(pedido_id=pedido.id_pedido).one().id_venta)
        assert float(venta.descuento_manual_monto) == 5000
        assert float(venta.descuento_monto) == 35000
        assert float(venta.total) == 70000
        assert _efectivo(sesion_id) == 100000


def test_sena_por_tarjeta_no_suma_efectivo_pero_se_descuenta_igual():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Cobro Sena 3', 'cobro_sena_3')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(
            cliente_id, usuario_id, pedido.id_pedido,
            {'monto': 30000, 'metodo_pago': 'tarjeta', 'referencia': 'VOUCHER-9'},
        )
        assert _efectivo(sesion_id) == 0

        cobrar_pedido(cliente_id, usuario_id, pedido.id_pedido, {'metodo_pago': 'efectivo'})
        assert _efectivo(sesion_id) == 75000  # solo el saldo entra como efectivo
        assert pedido.adelantos.one().estado == ADELANTO_APLICADO


def test_encargo_sin_sena_se_cobra_por_el_total():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Cobro Sena 4', 'cobro_sena_4')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        cobrar_pedido(cliente_id, usuario_id, pedido.id_pedido, {'metodo_pago': 'efectivo'})
        pago = GastronomiaPedidoPago.query.filter_by(pedido_id=pedido.id_pedido).one()
        assert float(pago.descuento_monto) == 0
        assert float(pago.total_cobrado) == 105000
        assert _efectivo(sesion_id) == 105000


def test_cobrar_un_encargo_que_no_paso_por_produccion_descuenta_el_stock_una_vez():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Cobro Sena 5', 'cobro_sena_5')
    insumo_id = _agregar_insumo(app, cliente_id, 'Harina cobro', 100)

    with app.app_context():
        guardar_receta(cliente_id, producto_id, {'items': [{'insumo_id': insumo_id, 'cantidad': 2}]})
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        db.session.expire_all()
        assert db.session.get(Producto, insumo_id).stock_actual == 100

        cobrar_pedido(cliente_id, usuario_id, pedido.id_pedido, {'metodo_pago': 'efectivo'})
        db.session.expire_all()
        assert db.session.get(Producto, insumo_id).stock_actual == 86

    with app.app_context():
        otro = _encargo(cliente_id, usuario_id, producto_id)
        cambiar_estado_pedido(cliente_id, otro.id_pedido, 'preparando')
        cobrar_pedido(cliente_id, usuario_id, otro.id_pedido, {'metodo_pago': 'efectivo'})
        db.session.expire_all()
        assert db.session.get(Producto, insumo_id).stock_actual == 72  # 14 mas, no 28


def test_anular_la_venta_devuelve_la_sena_a_pendiente_y_se_puede_resolver_despues():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Cobro Sena 6', 'cobro_sena_6')
    insumo_id = _agregar_insumo(app, cliente_id, 'Harina anula', 100)

    with app.app_context():
        guardar_receta(cliente_id, producto_id, {'items': [{'insumo_id': insumo_id, 'cantidad': 2}]})
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 30000})
        cobrar_pedido(cliente_id, usuario_id, pedido.id_pedido, {'metodo_pago': 'efectivo'})
        assert _efectivo(sesion_id) == 105000

        anular_venta_gastronomica(cliente_id, pedido.id_pedido, usuario_id, motivo='Error de cobro')

        db.session.expire_all()
        pedido = db.session.get(GastronomiaPedido, pedido.id_pedido)
        assert pedido.estado == 'cancelado'
        assert pedido.adelantos.one().estado == ADELANTO_VIGENTE  # vuelve a quedar pendiente de decision
        assert pedido.adelantos.one().id_venta is None
        assert db.session.get(Producto, insumo_id).stock_actual == 100
        assert _efectivo(sesion_id) == 30000  # se revirtio el saldo, la sena sigue en caja

        # La sena no se puede olvidar: el pedido ya esta cancelado y falta decidir.
        with pytest.raises(ValueError, match='Elegi que hacer'):
            cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido)
        cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido, opcion='devolver_todo')
        assert pedido.adelantos.one().estado == ADELANTO_DEVUELTO
        assert _efectivo(sesion_id) == 0
        with pytest.raises(ValueError, match='ya esta cancelado'):
            cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido)


def test_la_cola_central_rechaza_encargos_con_sena_vigente():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Cobro Sena 7', 'cobro_sena_7')

    with app.app_context():
        con_sena = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, con_sena.id_pedido, {'monto': 30000})
        with pytest.raises(ValueError, match='caja de gastronomia'):
            crear_cola_cobro_central_desde_pedido(con_sena, usuario_id)

        sin_sena = _encargo(cliente_id, usuario_id, producto_id)
        assert crear_cola_cobro_central_desde_pedido(sin_sena, usuario_id).id_origen == sin_sena.id_pedido


def test_cobro_http_de_la_caja_muestra_el_descuento_por_sena():
    import re

    from test_gastronomia_caja import _csrf, _loguear

    app = create_app('testing')
    client = app.test_client()
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Cobro Sena 8', 'cobro_sena_8')
    _loguear(client, app, 'cobro_sena_8')
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))

    with app.app_context():
        pedido_id = _encargo(cliente_id, usuario_id, producto_id).id_pedido
        registrar_adelanto(cliente_id, usuario_id, pedido_id, {'monto': 30000})

    respuesta = client.post(
        f'/api/gastronomia/caja/pedidos/{pedido_id}/cobrar',
        json={'metodo_pago': 'efectivo'},
        headers={'X-CSRFToken': csrf},
    )
    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)
    pago = respuesta.get_json()['pedido']['pago']
    assert pago['subtotal'] == 105000
    assert pago['descuento_monto'] == 30000
    assert pago['total_cobrado'] == 75000
    assert re.fullmatch(r'efectivo', pago['metodo_pago'])
