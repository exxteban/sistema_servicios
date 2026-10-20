"""Fase 1 (paso 2) del plan de pasteleria: el encargo descuenta stock al entrar en produccion."""
from datetime import datetime

from app import create_app, db
from app.models import MovimientoStock, Producto, Usuario
from gastronomia.models import GastronomiaPedidoItem, GastronomiaProducto
from gastronomia.services.pedido_service import (
    actualizar_pedido_abierto,
    cambiar_estado_pedido,
    crear_pedido,
)
from gastronomia.services.stock_service import guardar_receta
from gastronomia.stock_models import GastronomiaPedidoItemConsumo
from test_gastronomia_pedidos import _agregar_insumo, _crear_menu_para_pedidos


PROGRAMADA = datetime(2030, 6, 1, 15, 0)


def _preparar(app, nombre: str, username: str, *, stock_insumo=10, receta=2):
    cliente_id, producto_id, _ = _crear_menu_para_pedidos(app, nombre, username)
    insumo_id = _agregar_insumo(app, cliente_id, f'Harina {username}', stock_insumo)
    with app.app_context():
        guardar_receta(cliente_id, producto_id, {'items': [{'insumo_id': insumo_id, 'cantidad': receta}]})
        usuario_id = Usuario.query.filter_by(username=username).first().id_usuario
    return cliente_id, usuario_id, producto_id, insumo_id


def _stock(insumo_id: int) -> int:
    db.session.expire_all()
    return int(db.session.get(Producto, insumo_id).stock_actual)


def _pedido(cliente_id, usuario_id, producto_id, cantidad=2, *, encargo: bool):
    kwargs = {'es_encargo': True, 'fecha_programada': PROGRAMADA} if encargo else {}
    return crear_pedido(
        cliente_id,
        usuario_id,
        {'tipo_pedido': 'retiro', 'nombre_cliente': 'Ana', 'items': [{'producto_id': producto_id, 'cantidad': cantidad}]},
        **kwargs,
    )


def test_encargo_no_consume_al_crearse_y_consume_al_pasar_a_preparando():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, insumo_id = _preparar(app, 'Stock Dif 1', 'stock_dif_1')

    with app.app_context():
        pedido = _pedido(cliente_id, usuario_id, producto_id, 2, encargo=True)
        pedido_id = pedido.id_pedido
        assert pedido.es_encargo is True
        assert pedido.fecha_programada == PROGRAMADA
        assert _stock(insumo_id) == 10
        assert not _consumos_de(pedido_id)

        cambiar_estado_pedido(cliente_id, pedido_id, 'enviado_cocina')
        assert _stock(insumo_id) == 10  # enviar a produccion todavia no consume

        cambiar_estado_pedido(cliente_id, pedido_id, 'preparando')
        assert _stock(insumo_id) == 6  # 2 unidades x receta 2

        cambiar_estado_pedido(cliente_id, pedido_id, 'listo')
        cambiar_estado_pedido(cliente_id, pedido_id, 'entregado')
        assert _stock(insumo_id) == 6  # nunca se consume dos veces
        assert len(_consumos_de(pedido_id)) == 1


def test_cancelar_encargo_antes_de_produccion_no_toca_el_stock_y_reabrir_no_consume():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, insumo_id = _preparar(app, 'Stock Dif 2', 'stock_dif_2')

    with app.app_context():
        pedido_id = _pedido(cliente_id, usuario_id, producto_id, 2, encargo=True).id_pedido

        cambiar_estado_pedido(cliente_id, pedido_id, 'cancelado')
        assert _stock(insumo_id) == 10
        assert MovimientoStock.query.filter_by(id_producto=insumo_id).count() == 0

        cambiar_estado_pedido(cliente_id, pedido_id, 'abierto')  # reabrir
        assert _stock(insumo_id) == 10

        cambiar_estado_pedido(cliente_id, pedido_id, 'preparando')
        assert _stock(insumo_id) == 6


def test_cancelar_encargo_en_produccion_restaura_y_reabrir_no_vuelve_a_consumir_solo():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, insumo_id = _preparar(app, 'Stock Dif 3', 'stock_dif_3')

    with app.app_context():
        pedido_id = _pedido(cliente_id, usuario_id, producto_id, 2, encargo=True).id_pedido
        cambiar_estado_pedido(cliente_id, pedido_id, 'preparando')
        assert _stock(insumo_id) == 6

        cambiar_estado_pedido(cliente_id, pedido_id, 'cancelado')
        assert _stock(insumo_id) == 10

        cambiar_estado_pedido(cliente_id, pedido_id, 'abierto')
        assert _stock(insumo_id) == 10  # vuelve a la espera, sin consumir

        cambiar_estado_pedido(cliente_id, pedido_id, 'preparando')
        assert _stock(insumo_id) == 6
        assert len(_consumos_de(pedido_id, activos=True)) == 1


def test_editar_encargo_abierto_no_mueve_stock():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, insumo_id = _preparar(app, 'Stock Dif 4', 'stock_dif_4')

    with app.app_context():
        pedido_id = _pedido(cliente_id, usuario_id, producto_id, 1, encargo=True).id_pedido
        actualizar_pedido_abierto(cliente_id, pedido_id, {
            'tipo_pedido': 'retiro',
            'nombre_cliente': 'Ana',
            'items': [{
                'producto_id': producto_id,
                'cantidad': 3,
                'texto_personalizado': '  Feliz cumple Ana  ',
            }],
        })
        assert _stock(insumo_id) == 10
        item = GastronomiaPedidoItem.query.filter_by(pedido_id=pedido_id).one()
        assert item.cantidad == 3
        assert item.texto_personalizado == 'Feliz cumple Ana'

        cambiar_estado_pedido(cliente_id, pedido_id, 'preparando')
        assert _stock(insumo_id) == 4  # 3 x receta 2


def test_encargo_de_producto_con_stock_directo_tambien_difiere():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, _ = _preparar(app, 'Stock Dif 5', 'stock_dif_5')

    with app.app_context():
        producto = db.session.get(GastronomiaProducto, producto_id)
        producto.control_stock_venta = True
        producto.stock_disponible = 5
        db.session.commit()

        pedido_id = _pedido(cliente_id, usuario_id, producto_id, 2, encargo=True).id_pedido
        assert db.session.get(GastronomiaProducto, producto_id).stock_disponible == 5

        cambiar_estado_pedido(cliente_id, pedido_id, 'preparando')
        db.session.expire_all()
        assert db.session.get(GastronomiaProducto, producto_id).stock_disponible == 3

        cambiar_estado_pedido(cliente_id, pedido_id, 'cancelado')
        db.session.expire_all()
        assert db.session.get(GastronomiaProducto, producto_id).stock_disponible == 5


def test_pedido_comun_sigue_consumiendo_al_crear():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id, insumo_id = _preparar(app, 'Stock Dif 6', 'stock_dif_6')

    with app.app_context():
        pedido = _pedido(cliente_id, usuario_id, producto_id, 2, encargo=False)
        pedido_id = pedido.id_pedido
        assert pedido.es_encargo is False
        assert _stock(insumo_id) == 6  # consumo al crear, como siempre

        cambiar_estado_pedido(cliente_id, pedido_id, 'cancelado')
        assert _stock(insumo_id) == 10

        cambiar_estado_pedido(cliente_id, pedido_id, 'abierto')  # reabrir consume todo de nuevo
        assert _stock(insumo_id) == 6

        cambiar_estado_pedido(cliente_id, pedido_id, 'preparando')
        assert _stock(insumo_id) == 6


def _consumos_de(pedido_id: int, *, activos: bool = False):
    consulta = (
        GastronomiaPedidoItemConsumo.query
        .join(GastronomiaPedidoItem, GastronomiaPedidoItem.id_item == GastronomiaPedidoItemConsumo.item_id)
        .filter(GastronomiaPedidoItem.pedido_id == pedido_id)
    )
    if activos:
        consulta = consulta.filter(GastronomiaPedidoItemConsumo.restaurado.is_(False))
    return consulta.all()
