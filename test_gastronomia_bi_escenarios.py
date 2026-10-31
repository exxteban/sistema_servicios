"""Escenarios ficticios de la fase 0 del plan de BI: negocio nuevo, comida rapida con delivery y cafeteria."""
from datetime import timedelta

from app import create_app
from gastronomia.services.bi.canales import indicadores_canales
from gastronomia.services.bi.crecer import resumen_crecer_seguro
from gastronomia.services.bi.historial import historial_clientes
from gastronomia.services.bi.pedidos_validos import GRUPO_DESCONOCIDO, GRUPO_PLATAFORMA, GRUPO_PROPIO
from test_gastronomia_bi_fase0 import (
    LUNES,
    _crear_cliente_final,
    _crear_negocio,
    _crear_pedido,
    _crear_producto,
    _periodo,
)


def test_negocio_nuevo_sin_historial_no_muestra_ceros_ni_falla():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'Escenario Nuevo', 'esc_nuevo')
    with app.app_context():
        indicadores = indicadores_canales(cliente_id, _periodo())
        crecer = resumen_crecer_seguro(cliente_id, _periodo())
        historial = historial_clientes(cliente_id)

    assert indicadores['total_pedidos'] == 0
    assert indicadores['identidad']['porcentaje'] is None
    assert indicadores['grupos'][GRUPO_PROPIO]['participacion'] is None
    assert indicadores['semanas'] == []
    assert crecer is not None
    assert historial == {}


def test_comida_rapida_con_delivery_separa_canales_y_cobertura():
    app = create_app('testing')
    cliente_id, usuario_id, categoria_id = _crear_negocio(app, 'Escenario Delivery', 'esc_delivery')
    producto_id = _crear_producto(app, cliente_id, categoria_id, 'Hamburguesa')
    final_id = _crear_cliente_final(app, cliente_id, '+595981500001')
    # Mostrador con celular, tienda con cliente final, y dos pedidos de PedidosYa sin identificar.
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES, celular='0981 500 002')
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES + timedelta(days=1), origen='tienda_online', cliente_final_id=final_id)
    for dia in (2, 3):
        _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES + timedelta(days=dia), canales_item=('pedidosya',))
    # Un pedido anulado y uno con celular mal formado no inflan la cobertura.
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES, estado='cancelado', celular='0981 500 003')
    _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES + timedelta(days=4), celular='12345')

    with app.app_context():
        indicadores = indicadores_canales(cliente_id, _periodo())

    grupos = indicadores['grupos']
    assert indicadores['total_pedidos'] == 5
    assert grupos[GRUPO_PROPIO]['pedidos'] == 3
    assert grupos[GRUPO_PLATAFORMA]['pedidos'] == 2
    assert grupos[GRUPO_DESCONOCIDO]['pedidos'] == 0
    assert grupos[GRUPO_PROPIO]['identidad']['identificados'] == 2
    assert grupos[GRUPO_PLATAFORMA]['identidad']['identificados'] == 0
    assert indicadores['identidad']['telefonos_invalidos'] == 1
    assert indicadores['identidad']['porcentaje'] == 40.0


def test_cafeteria_de_mostrador_sin_telefonos_tiene_cobertura_cero_y_cola_vacia():
    app = create_app('testing')
    cliente_id, usuario_id, categoria_id = _crear_negocio(app, 'Escenario Cafe', 'esc_cafe')
    producto_id = _crear_producto(app, cliente_id, categoria_id, 'Cafe con leche', precio=8000)
    for dia in range(5):
        _crear_pedido(app, cliente_id, usuario_id, producto_id, LUNES + timedelta(days=dia))

    with app.app_context():
        indicadores = indicadores_canales(cliente_id, _periodo())
        historial = historial_clientes(cliente_id)

    # Con pedidos y ninguno identificado la cobertura es 0 %, distinta de "sin datos" (None).
    assert indicadores['identidad']['porcentaje'] == 0.0
    assert indicadores['grupos'][GRUPO_PROPIO]['pedidos'] == 5
    assert historial == {}
