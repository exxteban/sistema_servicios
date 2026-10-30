from datetime import datetime, timedelta

import pytest

from app import db
from app.models import Cliente
from gastronomia.models import GastronomiaCategoria as Categoria, GastronomiaProducto as Producto
from gastronomia.channel_models import GastronomiaProductoPrecioCanal as Precio
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaRegla as Regla, GastronomiaSugerenciaExcluido as Excluido,
    GastronomiaSugerenciaPar as Par, GastronomiaSugerenciaOrigen as Origen,
    GastronomiaSugerenciaEstadistica as Estadistica, GastronomiaSugerenciaConfig as Config,
)
from gastronomia.services.sugerencias.candidatos import previsualizar
from gastronomia.services.sugerencias.consulta_pos import consultar
from test_gastronomia_sugerencias import datos  # noqa: F401


def menu(datos):
    cliente, _, _ = datos
    categorias = {}
    productos = {}
    for nombre, categoria, precio in [
        ('Gus Doble', 'Hamburguesas', 30000), ('Otra Doble', 'Hamburguesas', 32000),
        ('Papas fritas', 'Para acompañar', 12000), ('Agua mineral', 'Bebidas sin gas', 5000),
        ('Coca Personal', 'Bebidas con gas', 7000), ('Coca 2 litros', 'Bebidas con gas', 15000),
        ('Pepsi', 'Bebidas con gas', 8000), ('Jugo naranja', 'Bebidas sin gas', 6000),
        ('Cerveza', 'Bebidas con gas', 7000), ('Cafe', 'Cafes', 10000),
        ('Medialuna', 'Para acompañar', 8000), ('Chipa', 'Para acompañar', 5000),
    ]:
        if categoria not in categorias:
            c = Categoria(cliente_id=cliente, nombre=categoria)
            db.session.add(c)
            db.session.flush()
            categorias[categoria] = c.id_categoria
        p = Producto(cliente_id=cliente, categoria_id=categorias[categoria], nombre=nombre, precio=precio)
        db.session.add(p)
        db.session.flush()
        productos[nombre] = p.id_producto
    db.session.commit()
    return cliente, productos


def sugeridas(cliente, carrito, **kwargs):
    return previsualizar(cliente, carrito, **kwargs)['sugerencias']


def test_arranque_hamburgueseria_sin_ventas_ni_reglas(datos):
    cliente, p = menu(datos)
    r = sugeridas(cliente, [p['Gus Doble']])
    assert [s['id_producto'] for s in r[:3]] == [p['Papas fritas'], p['Coca Personal'], p['Agua mineral']]
    assert p['Otra Doble'] not in [s['id_producto'] for s in r]
    assert p['Cerveza'] not in [s['id_producto'] for s in r]
    assert all(s['fuente'] == 'complemento' and s['soporte'] is None for s in r)
    assert all(s['motivo'] == 'Complemento habitual para hamburguesas' for s in r)
    assert Regla.query.count() == 0 and Par.query.count() == 0
    assert not db.session.new and not db.session.dirty


@pytest.mark.parametrize('campo,valor', [('activo', False), ('visible', False), ('disponible', False), ('stock_disponible', 0)])
def test_disponibilidad_y_siguiente_bebida_valida(datos, campo, valor):
    cliente, p = menu(datos)
    cola = db.session.get(Producto, p['Coca Personal'])
    if campo == 'stock_disponible':
        cola.control_stock_venta = True
    setattr(cola, campo, valor)
    db.session.commit()
    r = sugeridas(cliente, [p['Gus Doble']])
    ids = [s['id_producto'] for s in r]
    assert p['Coca Personal'] not in ids and p['Pepsi'] in ids
    assert p['Coca 2 litros'] not in ids  # una sola gaseosa; prefiere la más económica


def test_carrito_no_repite_tipo_y_comida_ya_incluida(datos):
    cliente, p = menu(datos)
    r = sugeridas(cliente, [p['Gus Doble'], p['Coca Personal']])
    assert [s['id_producto'] for s in r] == [p['Papas fritas']]
    r = sugeridas(cliente, [p['Gus Doble'], p['Papas fritas']])
    assert p['Papas fritas'] not in [s['id_producto'] for s in r]
    origen = db.session.get(Producto, p['Gus Doble'])
    origen.nombre = 'Hamburguesa con papas y Coca'
    db.session.commit()
    assert sugeridas(cliente, [origen.id_producto]) == []


def test_prohibiciones_exclusiones_y_fatiga_siempre_ganan(datos):
    cliente, p = menu(datos)
    db.session.add(Regla(cliente_id=cliente, tipo='prohibir', origen_tipo='producto', origen_id=p['Gus Doble'],
                         destino_tipo='producto', destino_id=p['Papas fritas']))
    db.session.add(Excluido(cliente_id=cliente, tipo='producto', id_ref=p['Coca Personal']))
    db.session.add(Estadistica(cliente_id=cliente, id_origen=p['Gus Doble'], id_destino=p['Agua mineral'],
                              oculto_hasta=datetime.utcnow() + timedelta(days=30)))
    db.session.commit()
    ids = [s['id_producto'] for s in sugeridas(cliente, [p['Gus Doble']])]
    assert not {p['Papas fritas'], p['Coca Personal'], p['Agua mineral']} & set(ids)
    assert p['Pepsi'] in ids


def test_reglas_y_asociaciones_van_antes_que_complementos(datos):
    cliente, p = menu(datos)
    origen = p['Gus Doble']
    db.session.add(Regla(cliente_id=cliente, origen_tipo='producto', origen_id=origen,
                         destino_tipo='producto', destino_id=p['Cafe']))
    db.session.add(Origen(cliente_id=cliente, nivel='producto', id_origen=origen, pedidos=12))
    db.session.add(Par(cliente_id=cliente, nivel='producto', id_origen=origen, id_destino=p['Jugo naranja'],
                       soporte=4, confianza=.2, lift=2, puntaje=.001))
    db.session.commit()
    r = sugeridas(cliente, [origen])
    assert [s['fuente'] for s in r[:2]] == ['regla', 'producto']
    assert [s['id_producto'] for s in r[:2]] == [p['Cafe'], p['Jugo naranja']]
    assert len({s['id_producto'] for s in r}) == len(r)


def test_precio_del_canal_y_aislamiento(datos):
    cliente, p = menu(datos)
    db.session.add(Precio(cliente_id=cliente, producto_id=p['Gus Doble'], canal='pedidosya', precio=10000))
    db.session.add(Precio(cliente_id=cliente, producto_id=p['Papas fritas'], canal='pedidosya', precio=15000))
    db.session.commit()
    assert p['Papas fritas'] in [s['id_producto'] for s in sugeridas(cliente, [p['Gus Doble']])]
    assert p['Papas fritas'] not in [s['id_producto'] for s in sugeridas(cliente, [p['Gus Doble']], canal_precio='pedidosya')]
    otro = Cliente(nombre='Otro menú', ruc_ci='complementos-otro')
    db.session.add(otro)
    db.session.commit()
    assert sugeridas(otro.id_cliente, [p['Gus Doble']]) == []


@pytest.mark.parametrize('nombre,categoria', [('Pizza muzzarella', 'Pizzas'), ('Lomito', 'Sandwiches'), ('Empanada de carne', 'Empanadas')])
def test_otras_comidas_buscan_bebidas(datos, nombre, categoria):
    cliente, p = menu(datos)
    origen = db.session.get(Producto, p['Gus Doble'])
    origen.nombre = nombre
    r = sugeridas(cliente, [origen.id_producto])
    assert p['Coca Personal'] in [s['id_producto'] for s in r]
    assert p['Agua mineral'] in [s['id_producto'] for s in r]


def test_cafeteria_y_nombre_desconocido(datos):
    cliente, p = menu(datos)
    r = sugeridas(cliente, [p['Cafe']])
    assert [s['id_producto'] for s in r] == [p['Chipa']]
    assert r[0]['motivo'] == 'Complemento habitual para café'
    assert sugeridas(cliente, [datos[2][0]]) == []  # Plato 0, categoría genérica


def test_combos_y_complementos_compuestos_no_inventan_faltantes(datos):
    cliente, p = menu(datos)
    origen = db.session.get(Producto, p['Gus Doble'])
    origen.nombre = 'Combo Gus'
    db.session.commit()
    assert sugeridas(cliente, [origen.id_producto]) == []
    origen.nombre = 'Hamburguesa'
    db.session.get(Producto, p['Papas fritas']).nombre = 'Papas con hamburguesa'
    db.session.commit()
    assert p['Papas fritas'] not in [s['id_producto'] for s in sugeridas(cliente, [origen.id_producto])]


def test_bebida_y_guarnicion_incluidas_sin_nombre_de_marca(datos):
    cliente, p = menu(datos)
    origen = db.session.get(Producto, p['Gus Doble'])
    origen.nombre = 'Hamburguesa con bebida'
    db.session.commit()
    assert [s['id_producto'] for s in sugeridas(cliente, [origen.id_producto])] == [p['Papas fritas']]
    origen.descripcion = 'Incluye guarnición y bebida a elección'
    db.session.commit()
    assert sugeridas(cliente, [origen.id_producto]) == []


def test_modulo_apagado_sigue_sin_sugerir_y_activo_funciona_sin_reglas(datos):
    cliente, p = menu(datos)
    assert consultar(cliente, [p['Gus Doble']])['sugerencias'] == []
    db.session.add(Config(cliente_id=cliente, activo=True, mostrar_en_pos=True))
    db.session.commit()
    assert consultar(cliente, [p['Gus Doble']])['sugerencias'][0]['fuente'] == 'complemento'
