"""Reejecuta escenarios existentes sobre MariaDB real, siempre con una base nueva por caso."""
import inspect

import pytest
from flask import current_app
from sqlalchemy import event, text

from app import db
from app.models import MetodoPago
from gastronomia.models import GastronomiaProducto, GastronomiaPedidoPago
from gastronomia.services.pedido_service import crear_pedido, enviar_pedido_cocina
from gastronomia.services.caja_service import cobrar_pedido
from gastronomia.services.sugerencias.registro import registrar_seguro
from gastronomia.sugerencias_models import GastronomiaSugerenciaPedido
from test_gastronomia_sugerencias import datos  # noqa: F401
import test_gastronomia_sugerencias as calculo
import test_gastronomia_sugerencias_admin as admin
import test_gastronomia_sugerencias_medicion as medicion
import test_gastronomia_sugerencias_diagnostico as diagnostico
import test_gastronomia_sugerencias_diagnostico_pos as pos
import test_gastronomia_sugerencias_scheduler as scheduler
import test_gastronomia_sugerencias_complementos as complementos
from test_gastronomia_caja import _abrir_caja


pytestmark = pytest.mark.parametrize('datos', ['mysql'], indirect=True)
casos = []
for modulo in (calculo, admin, medicion, diagnostico, pos, scheduler, complementos):
    for nombre, funcion in vars(modulo).items():
        if not nombre.startswith('test_') or nombre.startswith('test_cli') or not inspect.isfunction(funcion):
            continue
        parametros = set(inspect.signature(funcion).parameters)
        if 'datos' in parametros and parametros <= {'datos', 'monkeypatch'}:
            casos.append(pytest.param(funcion, id=f'{modulo.__name__}:{nombre}'))


@pytest.mark.parametrize('caso', casos)
def test_escenario_mysql(datos, caso, monkeypatch):
    assert db.engine.dialect.name in {'mysql', 'mariadb'}
    argumentos = {'datos': datos}
    if 'monkeypatch' in inspect.signature(caso).parameters:
        argumentos['monkeypatch'] = monkeypatch
    caso(**argumentos)


@pytest.mark.parametrize('tabla', ['gastronomia_sugerencias_pedido', 'gastronomia_sugerencias_estadistica'])
def test_error_sql_real_no_revierte_pedido_cobro_cocina_o_stock(datos, tabla):
    cliente, usuario, ids = datos
    app = current_app._get_current_object()
    medicion.habilitar(cliente)
    producto = db.session.get(GastronomiaProducto, ids[0])
    producto.control_stock_venta, producto.stock_disponible = True, 10
    db.session.add(MetodoPago(nombre='Efectivo', activo=True, requiere_referencia=False))
    db.session.commit()
    _abrir_caja(app, 'sugerencias')
    data = medicion.payload(ids)
    pedido = crear_pedido(cliente, usuario, data)
    pedido_id = pedido.id_pedido
    def fallar(conn, cursor, statement, *args):
        if statement.lower().startswith(f'insert into {tabla}'):
            cursor.execute('INSERT INTO tabla_inexistente_qa_sugerencias VALUES (1)')
    event.listen(db.engine, 'before_cursor_execute', fallar)
    try:
        registrar_seguro(cliente, pedido_id, data)
    finally:
        event.remove(db.engine, 'before_cursor_execute', fallar)
    enviar_pedido_cocina(cliente, pedido_id)
    cobrar_pedido(cliente, usuario, pedido_id, {'metodo_pago': 'efectivo'})
    assert GastronomiaSugerenciaPedido.query.count() == 0
    assert GastronomiaPedidoPago.query.filter_by(pedido_id=pedido_id).one().id_venta
    assert float(db.session.get(GastronomiaProducto, ids[0]).stock_disponible) == 9
    assert db.session.execute(text('SELECT 1')).scalar_one() == 1
