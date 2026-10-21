"""Fase 2 del plan de pasteleria: venta por peso (tortas enteras por kilo)."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app import create_app, db
from app.models import DetalleVenta, SesionCaja, Usuario, Venta
from app.utils.helpers import now_local
from gastronomia.encargo_models import ADELANTO_DEVUELTO, ADELANTO_VIGENTE
from gastronomia.models import (
    GastronomiaClienteConfig,
    GastronomiaPedido,
    GastronomiaPedidoItem,
    GastronomiaPedidoPago,
    GastronomiaProducto,
)
from gastronomia.services.adelanto_service import cancelar_encargo, registrar_adelanto, sena_vigente
from gastronomia.services.caja_service import cobrar_pedido
from gastronomia.services.cliente_final_service import crear_pedido_publico_gastronomia
from gastronomia.services.encargo_peso_service import DevolucionNoPermitidaError, ajustar_peso_encargo
from gastronomia.services.encargo_service import crear_encargo
from gastronomia.services.menu_service import guardar_producto
from gastronomia.services.pedido_service import crear_pedido
from gastronomia.services.peso_service import formatear_kg, parsear_atajos, parsear_peso
from test_gastronomia_caja import _abrir_caja
from test_gastronomia_pedidos import _crear_menu_para_pedidos


def _local(app, nombre, username, *, peso=True, encargos=False):
    cliente_id, producto_id, _ = _crear_menu_para_pedidos(app, nombre, username)
    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one()
        config.venta_por_peso_activa = peso
        config.encargos_activo = encargos
        base = db.session.get(GastronomiaProducto, producto_id)
        torta = GastronomiaProducto(
            cliente_id=cliente_id, categoria_id=base.categoria_id, nombre='Torta chocolate',
            precio=80000, unidad_venta='kg',
        )
        db.session.add(torta)
        db.session.commit()
        usuario_id = Usuario.query.filter_by(username=username).first().id_usuario
        return cliente_id, usuario_id, producto_id, torta.id_producto


def _efectivo(sesion_id) -> float:
    db.session.expire_all()
    return float(db.session.get(SesionCaja, sesion_id).calcular_total_efectivo())


def test_parseo_y_formato_de_peso():
    assert parsear_peso('1,25') == parsear_peso('1.250')
    assert formatear_kg(parsear_peso('1.25')) == '1,250 kg'
    for invalido in ('', '0', '-1', '50.001', 'abc', '1.2345', 'nan', 'inf'):
        with pytest.raises(ValueError):
            parsear_peso(invalido)
    assert parsear_atajos('1,1.5,2') == [1.0, 1.5, 2.0]


def test_torta_por_kilo_es_una_linea_de_cantidad_uno_y_cobra_consistente():
    app = create_app('testing')
    cliente_id, usuario_id, _, torta_id = _local(app, 'Peso 1', 'peso_1')
    sesion_id = _abrir_caja(app, 'peso_1')

    with app.app_context():
        pedido = crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'mostrador',
            'items': [{'producto_id': torta_id, 'cantidad': 1, 'peso_kg': '1,25'}],
        })
        item = pedido.items.one()
        assert item.cantidad == 1
        assert float(item.peso_kg) == 1.25
        assert float(item.precio_por_kg) == 80000
        assert float(item.subtotal) == 100000
        assert float(item.precio_unitario) == 100000
        assert item.nombre_producto == 'Torta chocolate · 1,250 kg'
        assert float(pedido.total) == 100000

        cobrar_pedido(cliente_id, usuario_id, pedido.id_pedido, {'metodo_pago': 'efectivo'})
        venta = db.session.get(Venta, GastronomiaPedidoPago.query.filter_by(pedido_id=pedido.id_pedido).one().id_venta)
        detalle = DetalleVenta.query.filter_by(id_venta=venta.id_venta).one()
        assert (detalle.cantidad, float(detalle.subtotal), float(venta.total)) == (1, 100000, 100000)
        assert _efectivo(sesion_id) == 100000


@pytest.mark.parametrize('item, mensaje', [
    ({'cantidad': 2, 'peso_kg': '1'}, 'una linea con su peso'),
    ({'cantidad': 1}, 'peso'),
    ({'cantidad': 1, 'peso_kg': '0'}, 'mayor a cero'),
    ({'cantidad': 1, 'peso_kg': '-2'}, 'mayor a cero'),
    ({'cantidad': 1, 'peso_kg': '80'}, 'superar'),
])
def test_peso_invalido_o_cantidad_mayor_a_uno_se_rechaza(item, mensaje):
    app = create_app('testing')
    cliente_id, usuario_id, _, torta_id = _local(app, 'Peso 2', 'peso_2')
    with app.app_context():
        with pytest.raises(ValueError, match=mensaje):
            crear_pedido(cliente_id, usuario_id, {
                'tipo_pedido': 'mostrador', 'items': [{'producto_id': torta_id, **item}],
            })
        assert GastronomiaPedido.query.count() == 0


def test_producto_por_kilo_no_recibe_promociones(monkeypatch):
    import app.services.tienda_promociones as promos

    mitad = SimpleNamespace(tipo='porcentaje', valor=50, id_promocion=None, cantidad_lleva=0, cantidad_paga=0)
    monkeypatch.setattr(promos, 'get_active_gastronomia_product_promotion', lambda *a, **k: mitad)
    monkeypatch.setattr(promos, 'attach_gastronomia_promotion_to_product_data', lambda producto, data, promo: data)
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, torta_id = _local(app, 'Peso 3', 'peso_3')
    with app.app_context():
        pedido = crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'mostrador',
            'items': [
                {'producto_id': torta_id, 'cantidad': 1, 'peso_kg': '1'},
                {'producto_id': producto_id, 'cantidad': 2},
            ],
        })
        torta, comun = pedido.items.order_by(GastronomiaPedidoItem.id_item.asc()).all()
        assert float(torta.subtotal) == 80000 and float(torta.descuento_linea or 0) == 0
        assert float(comun.subtotal) == 15000  # el producto comun si recibe la promo


def test_dos_tortas_de_pesos_distintos_no_se_pisan_el_nombre_en_la_venta():
    app = create_app('testing')
    cliente_id, usuario_id, _, torta_id = _local(app, 'Peso 4', 'peso_4')
    _abrir_caja(app, 'peso_4')
    with app.app_context():
        pedido = crear_pedido(cliente_id, usuario_id, {
            'tipo_pedido': 'mostrador',
            'items': [
                {'producto_id': torta_id, 'cantidad': 1, 'peso_kg': '1.2'},
                {'producto_id': torta_id, 'cantidad': 1, 'peso_kg': '2'},
            ],
        })
        cobrar_pedido(cliente_id, usuario_id, pedido.id_pedido, {'metodo_pago': 'efectivo'})
        venta_id = GastronomiaPedidoPago.query.filter_by(pedido_id=pedido.id_pedido).one().id_venta
        detalles = DetalleVenta.query.filter_by(id_venta=venta_id).order_by(DetalleVenta.id_detalle_venta).all()
        assert [d.item_nombre for d in detalles] == ['Torta chocolate', 'Torta chocolate']
        assert [float(d.subtotal) for d in detalles] == [96000, 160000]


def test_marcar_producto_por_kilo_requiere_el_flag_y_editar_lo_conserva():
    app = create_app('testing')
    cliente_id, _, producto_id, torta_id = _local(app, 'Peso 5', 'peso_5', peso=False)
    with app.app_context():
        comun = db.session.get(GastronomiaProducto, producto_id)
        datos = {'nombre': comun.nombre, 'categoria_id': comun.categoria_id, 'precio': '15000'}
        with pytest.raises(ValueError, match='no esta habilitada'):
            guardar_producto(cliente_id, {**datos, 'unidad_venta': 'kg'}, comun)
        db.session.rollback()

        torta = db.session.get(GastronomiaProducto, torta_id)
        guardar_producto(cliente_id, {'nombre': torta.nombre, 'categoria_id': torta.categoria_id, 'precio': '85000'}, torta)
        assert db.session.get(GastronomiaProducto, torta_id).unidad_venta == 'kg'

        GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one().venta_por_peso_activa = True
        db.session.commit()
        guardar_producto(cliente_id, {**datos, 'unidad_venta': 'kg'}, db.session.get(GastronomiaProducto, producto_id))
        assert db.session.get(GastronomiaProducto, producto_id).unidad_venta == 'kg'
        assert db.session.get(GastronomiaProducto, producto_id).to_dict()['unidad_venta'] == 'kg'


def test_pedido_web_con_producto_por_kilo_se_rechaza():
    app = create_app('testing')
    cliente_id, _, _, torta_id = _local(app, 'Peso 6', 'peso_6')
    with app.app_context():
        with pytest.raises(ValueError, match='se vende por peso'):
            crear_pedido_publico_gastronomia(cliente_id, {
                'nombre': 'Ana', 'celular': '0981123456', 'tipo_pedido': 'retiro',
                'items': [{'producto_id': torta_id, 'cantidad': 1}],
            })


def _encargo_por_peso(app, username):
    cliente_id, usuario_id, _, torta_id = _local(app, f'Peso {username}', username, encargos=True)
    sesion_id = _abrir_caja(app, username)
    with app.app_context():
        fecha = (now_local().replace(tzinfo=None) + timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0)
        pedido = crear_encargo(cliente_id, usuario_id, {
            'nombre_cliente': 'Ana', 'fecha_programada': fecha,
            'items': [{'producto_id': torta_id, 'cantidad': 1, 'peso_kg': '2'}],
        })
        registrar_adelanto(cliente_id, usuario_id, pedido.id_pedido, {'monto': 150000})
        item_id = pedido.items.one().id_item
        return cliente_id, usuario_id, pedido.id_pedido, item_id, sesion_id


def test_encargo_por_peso_se_ajusta_al_peso_real_y_devuelve_el_excedente():
    app = create_app('testing')
    cliente_id, usuario_id, pedido_id, item_id, sesion_id = _encargo_por_peso(app, 'peso_7')
    with app.app_context():
        assert _efectivo(sesion_id) == 150000

        resultado = ajustar_peso_encargo(cliente_id, usuario_id, pedido_id, item_id, '1.9')  # 152.000
        assert float(resultado['sena_devuelta']) == 0
        assert float(db.session.get(GastronomiaPedido, pedido_id).total) == 152000

        resultado = ajustar_peso_encargo(cliente_id, usuario_id, pedido_id, item_id, '1.8')  # 144.000
        pedido = db.session.get(GastronomiaPedido, pedido_id)
        assert float(resultado['sena_devuelta']) == 6000
        assert float(pedido.total) == 144000
        assert pedido.items.one().nombre_producto == 'Torta chocolate · 1,800 kg'
        assert float(sena_vigente(pedido)) == 144000
        assert pedido.adelantos.one().estado == ADELANTO_VIGENTE
        assert _efectivo(sesion_id) == 144000

        # Saldo cero: el cobro cierra el encargo sin mover mas efectivo.
        cobrar_pedido(cliente_id, usuario_id, pedido_id, {'metodo_pago': 'efectivo'})
        venta = db.session.get(Venta, GastronomiaPedidoPago.query.filter_by(pedido_id=pedido_id).one().id_venta)
        assert float(venta.total) == 0
        assert _efectivo(sesion_id) == 144000


def test_ajuste_que_obliga_a_devolver_exige_permiso_de_caja():
    app = create_app('testing')
    cliente_id, usuario_id, pedido_id, item_id, _ = _encargo_por_peso(app, 'peso_8')
    with app.app_context():
        with pytest.raises(DevolucionNoPermitidaError):
            ajustar_peso_encargo(cliente_id, usuario_id, pedido_id, item_id, '1.5', puede_devolver=False)
        pedido = db.session.get(GastronomiaPedido, pedido_id)
        assert float(pedido.total) == 160000  # no cambio nada
        assert float(pedido.items.one().peso_kg) == 2


def test_cancelar_despues_de_un_ajuste_devuelve_solo_lo_que_queda():
    app = create_app('testing')
    cliente_id, usuario_id, pedido_id, item_id, sesion_id = _encargo_por_peso(app, 'peso_9')
    with app.app_context():
        ajustar_peso_encargo(cliente_id, usuario_id, pedido_id, item_id, '1.8')
        cancelar_encargo(cliente_id, usuario_id, pedido_id, opcion='devolver_todo')
        adelanto = db.session.get(GastronomiaPedido, pedido_id).adelantos.one()
        assert adelanto.estado == ADELANTO_DEVUELTO
        assert float(adelanto.monto_devuelto) == 150000
        assert _efectivo(sesion_id) == 0
