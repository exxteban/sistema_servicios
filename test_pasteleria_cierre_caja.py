"""Fase 1 (paso 6) del plan de pasteleria: encargos en la lista de caja y en el cierre."""
from datetime import timedelta

from app import create_app, db
from app.models import Usuario
from app.utils.helpers import now_local
from gastronomia.models import GastronomiaClienteConfig, GastronomiaPedido
from gastronomia.services.adelanto_service import cancelar_encargo, registrar_adelanto
from gastronomia.services.caja_service import (
    cobrar_pedido,
    contar_pedidos_caja,
    listar_pedidos_caja,
    resumen_pedidos_impagos_para_cierre,
)
from gastronomia.services.encargo_cierre_service import informe_senas_sesion
from gastronomia.services.encargo_service import crear_encargo
from gastronomia.services.pedido_service import cambiar_estado_pedido, crear_pedido
from test_gastronomia_caja import _abrir_caja, _loguear
from test_gastronomia_pedidos import _crear_menu_para_pedidos


def _en_dias(dias: int, hora: int = 15):
    base = now_local().replace(tzinfo=None) + timedelta(days=dias)
    return base.replace(hour=hora, minute=0, second=0, microsecond=0)


def _local(app, nombre: str, username: str):
    cliente_id, producto_id, _ = _crear_menu_para_pedidos(app, nombre, username)
    with app.app_context():
        GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one().encargos_activo = True
        db.session.commit()
        usuario_id = Usuario.query.filter_by(username=username).first().id_usuario
    return cliente_id, usuario_id, producto_id, _abrir_caja(app, username)


def _encargo(cliente_id, usuario_id, producto_id, fecha, cantidad=7):
    # 7 x 15.000 = 105.000
    return crear_encargo(cliente_id, usuario_id, {
        'nombre_cliente': 'Ana',
        'fecha_programada': fecha,
        'items': [{'producto_id': producto_id, 'cantidad': cantidad}],
    })


def _vencer(pedido_id: int, dias_atras: int = 1):
    """Simula que llego (o paso) el dia de retiro sin pasar por la validacion de anticipo."""
    pedido = db.session.get(GastronomiaPedido, pedido_id)
    pedido.fecha_programada = _en_dias(-dias_atras)
    db.session.commit()


def test_encargo_futuro_no_aparece_en_la_lista_de_caja():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Cierre Enc 1', 'cierre_enc_1')

    with app.app_context():
        normal = crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_id, 'cantidad': 1}],
        })
        encargo = _encargo(cliente_id, usuario_id, producto_id, _en_dias(3))

        ids = [p.id_pedido for p in listar_pedidos_caja(cliente_id)]
        assert ids == [normal.id_pedido]
        assert contar_pedidos_caja(cliente_id) == 1

        # Listo antes de tiempo: ya se puede cobrar aunque el retiro sea otro dia.
        cambiar_estado_pedido(cliente_id, encargo.id_pedido, 'listo')
        assert encargo.id_pedido in [p.id_pedido for p in listar_pedidos_caja(cliente_id)]


def test_encargo_del_dia_aparece_en_la_lista_de_caja():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Cierre Enc 2', 'cierre_enc_2')

    with app.app_context():
        encargo = _encargo(cliente_id, usuario_id, producto_id, _en_dias(3))
        _vencer(encargo.id_pedido, dias_atras=0)
        assert [p.id_pedido for p in listar_pedidos_caja(cliente_id)] == [encargo.id_pedido]


def test_cierre_separa_encargos_futuros_y_no_exige_confirmacion():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Cierre Enc 3', 'cierre_enc_3')

    with app.app_context():
        futuro = _encargo(cliente_id, usuario_id, producto_id, _en_dias(4))
        registrar_adelanto(cliente_id, usuario_id, futuro.id_pedido, {'monto': 30000})
        cambiar_estado_pedido(cliente_id, futuro.id_pedido, 'listo')  # torta lista que se retira otro dia

        resumen = resumen_pedidos_impagos_para_cierre(cliente_id)
        assert resumen['terminados'] == []
        assert resumen['en_curso'] == []
        assert resumen['hay_terminados'] is False
        assert resumen['hay_encargos_pendientes'] is True
        item = resumen['encargos_pendientes'][0]
        assert item['id_pedido'] == futuro.id_pedido
        assert item['total'] == 105000
        assert item['sena'] == 30000
        assert item['saldo'] == 75000
        assert resumen['saldo_encargos_pendientes'] == 75000


def test_encargo_vencido_listo_requiere_confirmacion_por_el_saldo():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Cierre Enc 4', 'cierre_enc_4')

    with app.app_context():
        encargo = _encargo(cliente_id, usuario_id, producto_id, _en_dias(2))
        registrar_adelanto(cliente_id, usuario_id, encargo.id_pedido, {'monto': 30000})
        cambiar_estado_pedido(cliente_id, encargo.id_pedido, 'listo')
        _vencer(encargo.id_pedido)

        resumen = resumen_pedidos_impagos_para_cierre(cliente_id)
        assert resumen['encargos_pendientes'] == []
        assert [p['id_pedido'] for p in resumen['terminados']] == [encargo.id_pedido]
        assert resumen['total_terminados'] == 75000  # lo que falta cobrar es el saldo


def test_pedido_comun_mantiene_el_resumen_de_cierre():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Cierre Enc 5', 'cierre_enc_5')

    with app.app_context():
        pedido = crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'mostrador', 'items': [{'producto_id': producto_id, 'cantidad': 2}],
        })
        cambiar_estado_pedido(cliente_id, pedido.id_pedido, 'listo')
        resumen = resumen_pedidos_impagos_para_cierre(cliente_id)
        assert [p['total'] for p in resumen['terminados']] == [30000]
        assert resumen['hay_encargos_pendientes'] is False


def test_informe_de_senas_del_turno_separa_recibidas_devueltas_retenidas_y_aplicadas():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, sesion_id = _local(app, 'Cierre Enc 6', 'cierre_enc_6')

    with app.app_context():
        assert informe_senas_sesion(cliente_id, sesion_id) is None

        retirado = _encargo(cliente_id, usuario_id, producto_id, _en_dias(2))
        registrar_adelanto(cliente_id, usuario_id, retirado.id_pedido, {'monto': 20000})
        cobrar_pedido(cliente_id, usuario_id, retirado.id_pedido, {'metodo_pago': 'efectivo'})

        devuelto = _encargo(cliente_id, usuario_id, producto_id, _en_dias(3))
        registrar_adelanto(cliente_id, usuario_id, devuelto.id_pedido, {'monto': 10000})
        cancelar_encargo(cliente_id, usuario_id, devuelto.id_pedido, opcion='devolver_todo')

        parcial = _encargo(cliente_id, usuario_id, producto_id, _en_dias(4))
        registrar_adelanto(
            cliente_id, usuario_id, parcial.id_pedido, {'monto': 40000, 'metodo_pago': 'tarjeta', 'referencia': 'VOUCHER-1'},
        )
        cancelar_encargo(
            cliente_id, usuario_id, parcial.id_pedido, opcion='retener_parcial', monto_retenido=15000,
        )

        informe = informe_senas_sesion(cliente_id, sesion_id)
        assert informe['recibidas_total'] == 70000
        assert informe['recibidas_cantidad'] == 3
        assert {m['metodo']: m['monto'] for m in informe['recibidas_por_metodo']}['efectivo'] == 30000
        assert informe['devueltas_total'] == 35000  # 10.000 + 25.000 del retenido parcial
        assert informe['retenidas_total'] == 15000
        assert informe['retenidas_cantidad'] == 1
        assert informe['aplicadas_total'] == 20000


def test_pantalla_de_cierre_muestra_encargos_y_senas_sin_bloquear():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, usuario_id, producto_id, _ = _local(app, 'Cierre Enc 7', 'cierre_enc_7')
    _loguear(client, app, 'cierre_enc_7')

    with app.app_context():
        futuro = _encargo(cliente_id, usuario_id, producto_id, _en_dias(5))
        registrar_adelanto(cliente_id, usuario_id, futuro.id_pedido, {'monto': 30000})
        cambiar_estado_pedido(cliente_id, futuro.id_pedido, 'listo')

    html = client.get('/caja/cerrar').get_data(as_text=True)
    assert 'encargo(s) programado(s)' in html
    assert 'Señas de encargos del turno' in html
    assert 'confirmar_pedidos_pendientes' not in html  # la torta de otro dia no obliga a confirmar
