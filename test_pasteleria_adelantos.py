"""Fase 1 (paso 4) del plan de pasteleria: sena de encargos y su cancelacion."""
from datetime import timedelta

import pytest

from app import create_app, db
from app.models import MovimientoCaja, Producto, SesionCaja, Usuario
from app.utils.helpers import now_local
from gastronomia.encargo_models import (
    ADELANTO_DEVUELTO,
    ADELANTO_RETENIDO,
    ADELANTO_VIGENTE,
    GastronomiaPedidoAdelanto,
)
from gastronomia.models import GastronomiaClienteConfig, GastronomiaPedido
from gastronomia.services.adelanto_service import (
    REF_SENA_ENCARGO,
    cancelar_encargo,
    registrar_adelanto,
    resumen_sena,
    sena_vigente,
)
from gastronomia.services.encargo_service import actualizar_encargo, crear_encargo
from gastronomia.services.pedido_service import cambiar_estado_pedido
from gastronomia.services.stock_service import guardar_receta
from test_gastronomia_caja import _abrir_caja
from test_gastronomia_pedidos import _agregar_insumo, _crear_menu_para_pedidos


def _fecha():
    base = now_local().replace(tzinfo=None) + timedelta(days=3)
    return base.replace(hour=15, minute=0, second=0, microsecond=0)


def _local(app, nombre: str, username: str, *, caja=True, **parametros):
    """Local con encargos habilitados, una torta de 100.000 y (opcional) caja abierta."""
    cliente_id, producto_id, _ = _crear_menu_para_pedidos(app, nombre, username)
    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one()
        config.encargos_activo = True
        for clave, valor in parametros.items():
            setattr(config, clave, valor)
        db.session.commit()
        usuario_id = Usuario.query.filter_by(username=username).first().id_usuario
    sesion_id = _abrir_caja(app, username) if caja else None
    return cliente_id, usuario_id, producto_id, sesion_id


def _encargo(cliente_id, usuario_id, producto_id, cantidad=1):
    # El producto de prueba cuesta 15.000: 7 unidades = 105.000.
    return crear_encargo(cliente_id, usuario_id, {
        'nombre_cliente': 'Ana',
        'fecha_programada': _fecha(),
        'items': [{'producto_id': producto_id, 'cantidad': cantidad * 7}],
    })


def _movimientos(sesion_id):
    return MovimientoCaja.query.filter_by(
        id_sesion_caja=sesion_id, referencia_tipo=REF_SENA_ENCARGO,
    ).order_by(MovimientoCaja.id_movimiento_caja.asc()).all()


def _efectivo(sesion_id) -> float:
    db.session.expire_all()
    return float(db.session.get(SesionCaja, sesion_id).calcular_total_efectivo())


# --- Cobro de la sena -------------------------------------------------------

def test_sena_en_efectivo_entra_a_la_caja_del_operador():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Sena Ef', 'sena_ef')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        adelanto = registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 30000})

        assert adelanto.estado == ADELANTO_VIGENTE
        assert adelanto.metodo_pago == 'efectivo'
        assert adelanto.id_sesion_caja == sesion_id
        movimientos = _movimientos(sesion_id)
        assert len(movimientos) == 1
        assert movimientos[0].tipo == 'ingreso'
        assert float(movimientos[0].monto) == 30000
        assert movimientos[0].referencia_id == pedido.id_pedido
        assert adelanto.id_movimiento_caja == movimientos[0].id_movimiento_caja
        assert _efectivo(sesion_id) == 30000
        assert float(sena_vigente(pedido)) == 30000
        assert resumen_sena(pedido)['saldo'] == 75000


def test_sena_por_tarjeta_no_toca_el_efectivo_de_la_caja():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Sena Tj', 'sena_tj')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        adelanto = registrar_adelanto(
            cliente_id, usuario_id, pedido.id_pedido, {'monto': 20000, 'metodo_pago': 'tarjeta', 'referencia': 'VOUCHER-1'},
        )
        assert adelanto.metodo_pago == 'tarjeta'
        assert adelanto.id_movimiento_caja is None
        assert adelanto.id_sesion_caja == sesion_id
        assert _movimientos(sesion_id) == []
        assert _efectivo(sesion_id) == 0
        assert float(sena_vigente(pedido)) == 20000


def test_sena_exige_caja_abierta_flag_y_monto_valido():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Sena Val', 'sena_val', caja=False)

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        with pytest.raises(ValueError, match='caja'):
            registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 10000})
        assert pedido.adelantos.count() == 0

    _abrir_caja(app, 'sena_val')
    with app.app_context():
        for monto in (0, -5, 'abc', 105000, 200000):
            with pytest.raises(ValueError):
                registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': monto})
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 100000})
        with pytest.raises(ValueError, match='menor al total'):
            registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 5000})

        db.session.get(GastronomiaClienteConfig, GastronomiaClienteConfig.query.filter_by(
            cliente_id=cliente_id).one().id_config).encargos_activo = False
        db.session.commit()
        with pytest.raises(ValueError, match='no estan habilitados'):
            registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 1000})


def test_sena_no_se_registra_en_encargo_cancelado_ni_de_otro_cliente():
    app = create_app('testing')
    cliente_a, usuario_a, producto_a, _ = _local(app, 'Sena A', 'sena_a')
    cliente_b, usuario_b, _, _ = _local(app, 'Sena B', 'sena_b')

    with app.app_context():
        pedido = _encargo(cliente_a, usuario_a, producto_a)
        with pytest.raises(ValueError, match='Encargo no encontrado'):
            registrar_adelanto(cliente_b, usuario_b, pedido.id_pedido, {'monto': 1000})
        cancelar_encargo(cliente_a, usuario_a, pedido.id_pedido)
        with pytest.raises(ValueError, match='ya no admite'):
            registrar_adelanto(cliente_a, usuario_a, pedido.id_pedido, {'monto': 1000})


# --- Cancelacion: devolver / retener / retener parte --------------------------

def test_cancelar_con_sena_obliga_a_elegir_y_el_estado_generico_esta_bloqueado():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Sena Elige', 'sena_elige')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 30000})

        with pytest.raises(ValueError, match='Elegi que hacer'):
            cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido)
        with pytest.raises(ValueError, match='Elegi que hacer'):
            cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido, opcion='regalar')
        with pytest.raises(ValueError, match='Cancelalo desde Encargos'):
            cambiar_estado_pedido(cliente_id, pedido.id_pedido, 'cancelado')

        db.session.expire_all()
        assert db.session.get(GastronomiaPedido, pedido.id_pedido).estado == 'abierto'
        assert pedido.adelantos.filter_by(estado=ADELANTO_VIGENTE).count() == 1
        assert len(_movimientos(sesion_id)) == 1


def test_cancelar_devolviendo_todo_saca_el_efectivo_de_la_caja():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Sena Dev', 'sena_dev')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 30000})
        cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido, opcion='devolver_todo', motivo='Cliente desistio')

        db.session.expire_all()
        assert db.session.get(GastronomiaPedido, pedido.id_pedido).estado == 'cancelado'
        adelanto = pedido.adelantos.one()
        assert adelanto.estado == ADELANTO_DEVUELTO
        assert float(adelanto.monto_devuelto) == 30000
        assert adelanto.monto_retenido == 0
        assert adelanto.id_sesion_resolucion == sesion_id
        assert adelanto.usuario_resolucion_id == usuario_id
        assert adelanto.observacion == 'Cliente desistio'
        tipos = [m.tipo for m in _movimientos(sesion_id)]
        assert tipos == ['ingreso', 'egreso']
        assert adelanto.id_movimiento_devolucion is not None
        assert _efectivo(sesion_id) == 0  # la caja queda como antes de la sena


def test_cancelar_reteniendo_todo_no_crea_movimientos_y_el_dinero_sigue_en_caja():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Sena Ret', 'sena_ret')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 30000})
        cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido, opcion='retener_todo')

        adelanto = pedido.adelantos.one()
        assert adelanto.estado == ADELANTO_RETENIDO
        assert float(adelanto.monto_devuelto) == 0
        assert adelanto.monto_retenido == 30000
        assert len(_movimientos(sesion_id)) == 1  # solo el ingreso original
        assert _efectivo(sesion_id) == 30000
        db.session.expire_all()
        assert db.session.get(GastronomiaPedido, pedido.id_pedido).estado == 'cancelado'


def test_cancelar_reteniendo_una_parte_devuelve_el_resto():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Sena Parcial', 'sena_parcial')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 30000})

        for invalido in (None, 0, -1, 30000, 45000):
            with pytest.raises(ValueError, match='monto a retener'):
                cancelar_encargo(
                    cliente_id, usuario_id, pedido.id_pedido, opcion='retener_parcial', monto_retenido=invalido,
                )
        assert pedido.adelantos.one().estado == ADELANTO_VIGENTE

        cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido, opcion='retener_parcial', monto_retenido=10000)
        adelanto = pedido.adelantos.one()
        assert adelanto.estado == ADELANTO_RETENIDO
        assert float(adelanto.monto_devuelto) == 20000
        assert adelanto.monto_retenido == 10000
        egreso = [m for m in _movimientos(sesion_id) if m.tipo == 'egreso'][0]
        assert float(egreso.monto) == 20000
        assert _efectivo(sesion_id) == 10000


def test_varias_senas_reparten_la_retencion_en_orden_y_solo_devuelve_efectivo_por_caja():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Sena Varias', 'sena_varias')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 20000})  # efectivo
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 10000, 'metodo_pago': 'tarjeta', 'referencia': 'VOUCHER-1'})

        cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido, opcion='retener_parcial', monto_retenido=25000)

        primero, segundo = pedido.adelantos.order_by(GastronomiaPedidoAdelanto.id_adelanto.asc()).all()
        assert (primero.estado, float(primero.monto_devuelto)) == (ADELANTO_RETENIDO, 0)
        assert (segundo.estado, float(segundo.monto_devuelto)) == (ADELANTO_RETENIDO, 5000)
        # La devolucion de 5.000 fue por tarjeta: no sale efectivo de la caja.
        assert [m.tipo for m in _movimientos(sesion_id)] == ['ingreso']
        assert _efectivo(sesion_id) == 20000

    with app.app_context():
        otro = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, otro.id_pedido, {'monto': 20000})
        registrar_adelanto(cliente_id, usuario_id, otro.id_pedido, {'monto': 10000, 'metodo_pago': 'tarjeta', 'referencia': 'VOUCHER-1'})
        cancelar_encargo(cliente_id, usuario_id, otro.id_pedido, opcion='devolver_todo')
        egresos = [m for m in _movimientos(sesion_id) if m.tipo == 'egreso' and m.referencia_id == otro.id_pedido]
        assert [float(m.monto) for m in egresos] == [20000]  # solo la parte en efectivo


def test_cancelar_sin_caja_abierta_no_cambia_nada():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Sena SinCaja', 'sena_sincaja')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 30000})
        db.session.get(SesionCaja, sesion_id).estado = 'cerrada'
        db.session.commit()

        with pytest.raises(ValueError, match='caja'):
            cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido, opcion='devolver_todo')

        db.session.expire_all()
        assert db.session.get(GastronomiaPedido, pedido.id_pedido).estado == 'abierto'
        assert pedido.adelantos.one().estado == ADELANTO_VIGENTE


def test_opciones_de_cancelacion_se_pueden_limitar_por_cliente():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(
        app, 'Sena Opc', 'sena_opc', encargos_cancelacion_opciones='devolver_todo',
    )

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 30000})
        with pytest.raises(ValueError, match='devolver todo'):
            cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido, opcion='retener_todo')
        cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido, opcion='devolver_todo')
        assert pedido.adelantos.one().estado == ADELANTO_DEVUELTO


def test_cancelar_sin_sena_no_pide_opcion_y_cancelar_no_exige_el_flag():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Sena Sin', 'sena_sin')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)
        cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido)
        db.session.expire_all()
        assert db.session.get(GastronomiaPedido, pedido.id_pedido).estado == 'cancelado'
        with pytest.raises(ValueError, match='ya esta cancelado'):
            cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido)


def test_cancelar_encargo_en_produccion_restaura_el_stock():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Sena Stock', 'sena_stock')
    insumo_id = _agregar_insumo(app, cliente_id, 'Harina sena', 100)

    with app.app_context():
        guardar_receta(cliente_id, producto_id, {'items': [{'insumo_id': insumo_id, 'cantidad': 2}]})
        pedido = _encargo(cliente_id, usuario_id, producto_id)  # 7 unidades
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 30000})
        cambiar_estado_pedido(cliente_id, pedido.id_pedido, 'preparando')
        db.session.expire_all()
        assert db.session.get(Producto, insumo_id).stock_actual == 86

        cancelar_encargo(cliente_id, usuario_id, pedido.id_pedido, opcion='retener_todo')
        db.session.expire_all()
        assert db.session.get(Producto, insumo_id).stock_actual == 100


# --- Edicion ----------------------------------------------------------------

def test_editar_el_encargo_no_puede_dejar_el_total_por_debajo_de_la_sena():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Sena Edit', 'sena_edit')

    with app.app_context():
        pedido = _encargo(cliente_id, usuario_id, producto_id)  # 105.000
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 50000})

        with pytest.raises(ValueError, match='mayor que la sena'):
            actualizar_encargo(cliente_id, pedido.id_pedido, {
                'nombre_cliente': 'Ana',
                'items': [{'producto_id': producto_id, 'cantidad': 3}],  # 45.000 < 50.000
            })
        db.session.expire_all()
        assert float(db.session.get(GastronomiaPedido, pedido.id_pedido).total) == 105000

        editado = actualizar_encargo(cliente_id, pedido.id_pedido, {
            'nombre_cliente': 'Ana',
            'items': [{'producto_id': producto_id, 'cantidad': 4}],  # 60.000 > 50.000
        })
        assert float(editado.total) == 60000
