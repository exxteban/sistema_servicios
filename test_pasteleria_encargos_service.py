"""Fase 1 (paso 3) del plan de pasteleria: alta, edicion y consulta de encargos."""
from datetime import datetime, timedelta

import pytest

from app import create_app, db
from app.models import Usuario
from app.utils.helpers import now_local
from gastronomia.models import GastronomiaClienteConfig, GastronomiaPedido
from gastronomia.services.encargo_service import (
    EncargosDeshabilitadosError,
    actualizar_encargo,
    crear_encargo,
    enviar_a_produccion,
    limites_del_dia,
    listar_encargos,
    parsear_fecha_programada,
)
from gastronomia.services.pasteleria_flags import parametros_encargos
from gastronomia.services.pedido_service import cambiar_estado_pedido, crear_pedido, listar_pedidos_cocina
from test_gastronomia_pedidos import _crear_menu_para_pedidos


def _local(app, nombre: str, username: str, *, encargos=True, **parametros):
    cliente_id, producto_id, _ = _crear_menu_para_pedidos(app, nombre, username)
    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one()
        config.encargos_activo = encargos
        for clave, valor in parametros.items():
            setattr(config, clave, valor)
        db.session.commit()
        usuario_id = Usuario.query.filter_by(username=username).first().id_usuario
    return cliente_id, usuario_id, producto_id


def _datos(producto_id, fecha, **extra):
    return {
        'nombre_cliente': 'Ana',
        'fecha_programada': fecha,
        'items': [{'producto_id': producto_id, 'cantidad': 1}],
        **extra,
    }


def _futuro(dias=3, hora=15):
    base = now_local().replace(tzinfo=None) + timedelta(days=dias)
    return base.replace(hour=hora, minute=0, second=0, microsecond=0)


def test_encargos_requieren_el_flag_encendido():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(app, 'Enc Svc Off', 'enc_svc_off', encargos=False)

    with app.app_context():
        with pytest.raises(EncargosDeshabilitadosError):
            crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro()))
        assert GastronomiaPedido.query.filter_by(cliente_id=cliente_id).count() == 0


def test_crear_encargo_guarda_fecha_tipo_y_queda_abierto():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(app, 'Enc Svc Ok', 'enc_svc_ok')
    fecha = _futuro()

    with app.app_context():
        pedido = crear_encargo(cliente_id, usuario_id, _datos(
            producto_id, fecha.strftime('%Y-%m-%dT%H:%M'), notas='sin nueces',
        ))
        assert pedido.es_encargo is True
        assert pedido.tipo_pedido == 'retiro'
        assert pedido.origen_pedido == 'pos'
        assert pedido.estado == 'abierto'
        assert pedido.fecha_programada == fecha
        assert pedido.nombre_cliente == 'Ana'
        assert float(pedido.total) == 15000
        assert listar_pedidos_cocina(cliente_id) == []


def test_encargo_solo_admite_retiro_y_pide_nombre():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(app, 'Enc Svc Tipo', 'enc_svc_tipo')

    with app.app_context():
        for tipo in ('delivery', 'mesa', 'mostrador'):
            with pytest.raises(ValueError, match='solo admiten retiro'):
                crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(), tipo_pedido=tipo))
        with pytest.raises(ValueError, match='nombre del cliente'):
            crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(), nombre_cliente=''))
        assert GastronomiaPedido.query.filter_by(cliente_id=cliente_id).count() == 0


@pytest.mark.parametrize('valor', [None, '', 'manana', '2030-13-45 99:99'])
def test_fecha_invalida_se_rechaza(valor):
    with pytest.raises(ValueError):
        parsear_fecha_programada(valor)


def test_fecha_con_zona_se_convierte_a_hora_local_naive():
    app = create_app('testing')
    with app.app_context():
        fecha = parsear_fecha_programada('2030-06-01T18:00:00+00:00')
        assert fecha.tzinfo is None
        assert fecha == datetime(2030, 6, 1, 15, 0)  # Asuncion = UTC-3 en esa fecha


def test_fecha_pasada_y_anticipo_minimo():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(
        app, 'Enc Svc Anticipo', 'enc_svc_anticipo', encargos_anticipo_horas=48,
    )

    with app.app_context():
        with pytest.raises(ValueError, match='posterior'):
            crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(dias=-1)))
        with pytest.raises(ValueError, match='48 horas'):
            crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(dias=1, hora=0) + timedelta(hours=1)))
        assert crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(dias=5))).es_encargo


def test_tope_de_encargos_por_dia():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(
        app, 'Enc Svc Tope', 'enc_svc_tope', encargos_max_por_dia=2,
    )

    with app.app_context():
        primero = crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(4, 10)))
        crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(4, 11)))
        with pytest.raises(ValueError, match='limite de 2'):
            crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(4, 16)))

        # Otro dia no cuenta.
        crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(5, 10)))

        # Un cancelado libera el cupo.
        cambiar_estado_pedido(cliente_id, primero.id_pedido, 'cancelado')
        crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(4, 16)))


def test_sin_tope_no_hay_limite():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(app, 'Enc Svc Sin Tope', 'enc_svc_sin_tope')

    with app.app_context():
        assert parametros_encargos(cliente_id)['max_por_dia'] is None
        for hora in (9, 10, 11, 12):
            crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(4, hora)))


def test_actualizar_encargo_cambia_fecha_e_items_y_respeta_el_tope():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(
        app, 'Enc Svc Edit', 'enc_svc_edit', encargos_max_por_dia=1,
    )

    with app.app_context():
        pedido = crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(4, 10)))
        otro = crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(6, 10)))

        # Mismo dia: no se cuenta a si mismo contra el tope.
        editado = actualizar_encargo(cliente_id, pedido.id_pedido, _datos(
            producto_id, _futuro(4, 17), items=[{'producto_id': producto_id, 'cantidad': 2}],
        ))
        assert editado.fecha_programada == _futuro(4, 17)
        assert float(editado.total) == 30000

        # Mover a un dia ya completo se rechaza.
        with pytest.raises(ValueError, match='limite de 1'):
            actualizar_encargo(cliente_id, pedido.id_pedido, _datos(producto_id, _futuro(6, 12)))

        # Sin fecha en el payload conserva la actual.
        sin_fecha = _datos(producto_id, None, notas='nota nueva')
        del sin_fecha['fecha_programada']
        assert actualizar_encargo(cliente_id, otro.id_pedido, sin_fecha).fecha_programada == _futuro(6, 10)


def test_no_se_puede_editar_como_encargo_un_pedido_comun_ni_uno_en_produccion():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(app, 'Enc Svc Edit2', 'enc_svc_edit2')

    with app.app_context():
        comun = crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'retiro', 'nombre_cliente': 'Luis',
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        })
        with pytest.raises(ValueError, match='Encargo no encontrado'):
            actualizar_encargo(cliente_id, comun.id_pedido, _datos(producto_id, _futuro()))

        encargo = crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro()))
        enviar_a_produccion(cliente_id, encargo.id_pedido)
        with pytest.raises(ValueError, match='abiertos'):
            actualizar_encargo(cliente_id, encargo.id_pedido, _datos(producto_id, _futuro()))


def test_edicion_generica_no_puede_convertir_un_encargo_en_delivery():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(app, 'Enc Svc Generico', 'enc_svc_generico')

    from gastronomia.services.pedido_service import actualizar_pedido_abierto

    with app.app_context():
        encargo = crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro()))
        with pytest.raises(ValueError, match='solo admiten retiro'):
            actualizar_pedido_abierto(cliente_id, encargo.id_pedido, {
                'tipo_pedido': 'delivery', 'celular_cliente': '0981', 'direccion_entrega': 'Calle 1',
                'items': [{'producto_id': producto_id, 'cantidad': 1}],
            })
        assert listar_pedidos_cocina(cliente_id) == []


def test_enviar_a_produccion_lo_muestra_en_cocina():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(app, 'Enc Svc Prod', 'enc_svc_prod')

    with app.app_context():
        encargo = crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro()))
        assert listar_pedidos_cocina(cliente_id) == []

        enviado = enviar_a_produccion(cliente_id, encargo.id_pedido)
        assert enviado.estado == 'enviado_cocina'
        assert [p.id_pedido for p in listar_pedidos_cocina(cliente_id)] == [encargo.id_pedido]

        with pytest.raises(ValueError, match='abiertos'):
            enviar_a_produccion(cliente_id, encargo.id_pedido)


def test_listar_encargos_por_rango_ordenado_y_sin_comunes_ni_cancelados():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _local(app, 'Enc Svc Lista', 'enc_svc_lista')

    with app.app_context():
        tarde = crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(4, 17)))
        manana = crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(4, 9)))
        lejano = crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(9, 9)))
        cancelado = crear_encargo(cliente_id, usuario_id, _datos(producto_id, _futuro(4, 12)))
        cambiar_estado_pedido(cliente_id, cancelado.id_pedido, 'cancelado')
        crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'retiro', 'nombre_cliente': 'Luis',
            'items': [{'producto_id': producto_id, 'cantidad': 1}],
        })

        inicio, fin = limites_del_dia(_futuro(4))
        assert [p.id_pedido for p in listar_encargos(cliente_id, desde=inicio, hasta=fin)] == [
            manana.id_pedido, tarde.id_pedido,
        ]
        assert [p.id_pedido for p in listar_encargos(cliente_id)] == [
            manana.id_pedido, tarde.id_pedido, lejano.id_pedido,
        ]
        assert [p.id_pedido for p in listar_encargos(cliente_id, estados=['cancelado'])] == [cancelado.id_pedido]


def test_los_encargos_de_un_cliente_no_se_ven_en_otro():
    app = create_app('testing')
    cliente_a, usuario_a, producto_a = _local(app, 'Enc Svc A', 'enc_svc_a')
    cliente_b, _, _ = _local(app, 'Enc Svc B', 'enc_svc_b')

    with app.app_context():
        encargo = crear_encargo(cliente_a, usuario_a, _datos(producto_a, _futuro()))
        assert listar_encargos(cliente_b) == []
        with pytest.raises(ValueError, match='Encargo no encontrado'):
            actualizar_encargo(cliente_b, encargo.id_pedido, _datos(producto_a, _futuro()))
        with pytest.raises(ValueError, match='Encargo no encontrado'):
            enviar_a_produccion(cliente_b, encargo.id_pedido)
