from datetime import date, datetime, timedelta
import re

import pytest
from sqlalchemy import event

from app import db
from app.models import Cliente, Caja, SesionCaja, Venta
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem, GastronomiaPedidoPago, GastronomiaProducto
from gastronomia.services.sugerencias.aprendizaje import actualizar, factores
from gastronomia.services.sugerencias.candidatos import previsualizar
from gastronomia.services.sugerencias.medicion import resumen
from gastronomia.services.sugerencias.registro import registrar_seguro, restaurar_seguro, pares
from gastronomia.services.sugerencias.tarea import recalcular
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaPedido as Exposicion, GastronomiaSugerenciaEstadistica as Estadistica,
    GastronomiaSugerenciaConfig as Config, GastronomiaSugerenciaRegla as Regla,
)
from test_gastronomia_sugerencias import datos, pedido  # noqa: F401
from test_gastronomia_sugerencias_admin import pantalla  # noqa: F401
from test_gastronomia_sugerencias_pos import activar
from test_gastronomia_caja import _abrir_caja


def periodo():
    return {'desde': date.today() - timedelta(days=1), 'hasta': date.today() + timedelta(days=1)}


def habilitar(cliente):
    db.session.add(Config(cliente_id=cliente, activo=True, mostrar_en_pos=True))
    db.session.commit()


def payload(ids, aceptada=True):
    return {'tipo_pedido': 'mostrador', 'sugerencias': {'mostradas': [ids[:2], ids[:2]]},
            'items': [{'producto_id': ids[0], 'cantidad': 1},
                      {'producto_id': ids[1], 'cantidad': 1,
                       **({'origen_sugerencia': ids[0]} if aceptada else {})}]}


def test_registro_una_vez_por_par_y_solo_renglones_marcados(datos):
    cliente, _, ids = datos
    habilitar(cliente)
    p = pedido(datos, ids[:2] + [ids[1]])
    data = payload(ids)
    data['items'].append({'producto_id': ids[1], 'cantidad': 3})  # mismo destino por el menú
    registrar_seguro(cliente, p.id_pedido, data)
    registrar_seguro(cliente, p.id_pedido, data)
    db.session.expire_all()
    assert Exposicion.query.count() == 1
    e = Estadistica.query.one()
    assert (e.mostradas, e.tocadas, e.vendidas) == (1, 1, 0)
    actualizar(cliente, datetime.utcnow())
    db.session.commit()
    assert e.vendidas == 1
    s = resumen(cliente, periodo())
    assert (s['pedidos'], s['renglones'], s['sin_tocar']) == (1, 1, 0)
    restaurado = restaurar_seguro(cliente, p.id_pedido, p.to_dict())
    assert [i.get('origen_sugerencia') for i in restaurado['items']] == [None, ids[0], None]
    # Quitar lo aceptado y dejar el destino por el menú conserva la exposición histórica.
    data['items'][1].pop('origen_sugerencia')
    registrar_seguro(cliente, p.id_pedido, data)
    db.session.expire_all()
    assert Estadistica.query.one().tocadas == 1
    s = resumen(cliente, periodo())
    assert (s['pedidos'], s['renglones'], s['sin_tocar']) == (0, 0, 1)


def test_vendido_por_menu_cuenta_y_pendiente_no(datos):
    cliente, usuario, ids = datos
    habilitar(cliente)
    p = pedido(datos, ids[:2], pagado=False)
    registrar_seguro(cliente, p.id_pedido, payload(ids, False))
    actualizar(cliente, datetime.utcnow())
    db.session.commit()
    assert Estadistica.query.one().vendidas == 0
    assert resumen(cliente, periodo())['sin_tocar'] == 0
    db.session.add(GastronomiaPedidoPago(cliente_id=cliente, pedido_id=p.id_pedido, usuario_id=usuario))
    db.session.commit()
    for _ in range(2):
        actualizar(cliente, datetime.utcnow())
        db.session.commit()
    e = Estadistica.query.one()
    assert (e.mostradas, e.tocadas, e.vendidas, e.resueltas) == (1, 0, 1, 1)
    assert resumen(cliente, periodo())['sin_tocar'] == 1


def test_anulacion_y_fecha_cobro_corrigen_medicion(datos):
    cliente, usuario, ids = datos
    habilitar(cliente)
    p = pedido(datos, ids[:2])
    registrar_seguro(cliente, p.id_pedido, payload(ids))
    p.fecha_creacion = datetime.utcnow() - timedelta(days=400)
    caja = Caja(nombre='Medicion')
    db.session.add(caja)
    db.session.flush()
    sesion = SesionCaja(id_caja=caja.id_caja, id_usuario=usuario)
    db.session.add(sesion)
    db.session.flush()
    venta = Venta(id_cliente=cliente, id_sesion_caja=sesion.id_sesion,
                  subtotal=20, total=20, estado='completada')
    db.session.add(venta)
    db.session.flush()
    p.pago.id_venta = venta.id_venta
    db.session.commit()
    assert resumen(cliente, periodo())['pedidos'] == 1
    venta.estado = 'anulada'
    db.session.commit()
    assert resumen(cliente, periodo())['pedidos'] == 0
    actualizar(cliente, datetime.utcnow())
    db.session.commit()
    assert Estadistica.query.one().vendidas == 0
    venta.estado = 'completada'
    p.pago.fecha_pago -= timedelta(days=400)
    db.session.commit()
    assert resumen(cliente, periodo())['pedidos'] == 0


def test_fatiga_solo_con_cobrados_y_nueva_oportunidad(datos):
    cliente, usuario, ids = datos
    habilitar(cliente)
    db.session.add(Regla(cliente_id=cliente, origen_tipo='producto', origen_id=ids[0],
                         destino_tipo='producto', destino_id=ids[1]))
    for _ in range(30):
        p = pedido(datos, ids[:1], pagado=False)
        db.session.add(Exposicion(cliente_id=cliente, pedido_id=p.id_pedido, id_origen=ids[0], producto_id=ids[1]))
    db.session.commit()
    ahora = datetime.utcnow()
    actualizar(cliente, ahora)
    db.session.commit()
    e = Estadistica.query.one()
    assert (e.mostradas, e.resueltas, e.oculto_hasta) == (30, 0, None)
    assert factores(cliente)[(ids[0], ids[1])]['factor'] == 1
    for p in GastronomiaPedido.query.all():
        db.session.add(GastronomiaPedidoPago(cliente_id=cliente, pedido_id=p.id_pedido, usuario_id=usuario))
    db.session.commit()
    actualizar(cliente, ahora)
    db.session.commit()
    assert e.oculto_hasta == ahora + timedelta(days=30)
    assert (e.mostradas, e.tocadas, e.resueltas, e.vendidas) == (0, 0, 0, 0)
    assert previsualizar(cliente, ids[:1])['sugerencias'] == []
    assert 'aceptación' in previsualizar(cliente, ids[:1])['descartados'][0]['descarte']
    actualizar(cliente, ahora + timedelta(days=31))
    db.session.commit()
    assert not factores(cliente, ahora + timedelta(days=31))[(ids[0], ids[1])]['oculto']
    assert e.resueltas == 0  # las 30 anteriores no vuelven a ocultarla


def test_factor_acotado_y_aislamiento(datos):
    cliente, _, ids = datos
    otro = Cliente(nombre='Otro', ruc_ci='medicion-otro')
    db.session.add(otro)
    db.session.flush()
    for origen, ventas in [(ids[0], 1000), (ids[2], 0)]:
        db.session.add(Estadistica(cliente_id=cliente, id_origen=origen, id_destino=ids[1],
                                  mostradas=1000, resueltas=1000, vendidas=ventas))
    db.session.add(Estadistica(cliente_id=otro.id_cliente, id_origen=ids[0], id_destino=ids[1],
                              mostradas=9999, resueltas=9999, vendidas=0))
    db.session.commit()
    assert factores(cliente)[(ids[0], ids[1])]['factor'] == 1.5
    assert factores(cliente)[(ids[2], ids[1])]['factor'] == .5
    assert resumen(otro.id_cliente, periodo()) is None
    assert pares([[True, 2], ['1', 2], [1, 1], [-1, 2], [1, 2], [1, 2]]) == {(1, 2)}


def test_tocada_quitada_antes_de_guardar_y_origen_multiple(datos):
    cliente, _, ids = datos
    habilitar(cliente)
    p = pedido(datos, ids[:2])
    data = payload(ids)
    data['sugerencias'] = {'mostradas': [ids[:2], [ids[2], ids[1]]], 'tocadas': [[ids[2], ids[1]]]}
    registrar_seguro(cliente, p.id_pedido, data)
    db.session.expire_all()
    assert sum(e.tocadas for e in Estadistica.query.all()) == 2
    # La misma papa aceptada desde un origen no cuenta también como agregada por menú.
    assert resumen(cliente, periodo())['sin_tocar'] == 0
    data['items'][1].pop('origen_sugerencia')
    registrar_seguro(cliente, p.id_pedido, data)
    db.session.expire_all()
    assert Exposicion.query.filter_by(id_origen=ids[2]).one().tocada
    assert resumen(cliente, periodo())['sin_tocar'] == 1


def test_modulo_apagado_y_referencias_ajenas_no_registran(datos):
    cliente, _, ids = datos
    p = pedido(datos, ids[:2])
    registrar_seguro(cliente, p.id_pedido, payload(ids))
    assert Exposicion.query.count() == Estadistica.query.count() == 0
    habilitar(cliente)
    data = payload(ids)
    data['sugerencias']['mostradas'] = [[ids[0], 999999], [999999, ids[1]]]
    registrar_seguro(cliente, p.id_pedido, data)
    assert Exposicion.query.count() == Estadistica.query.count() == 0


def test_fallo_publicando_aprendizaje_preserva_contadores(datos, monkeypatch):
    cliente, _, ids = datos
    p = pedido(datos, ids[:2])
    db.session.add(Exposicion(cliente_id=cliente, pedido_id=p.id_pedido, id_origen=ids[0], producto_id=ids[1]))
    db.session.add(Estadistica(cliente_id=cliente, id_origen=ids[0], id_destino=ids[1], mostradas=77, vendidas=11))
    db.session.commit()
    def fallar(cliente_id, ahora):
        actualizar(cliente_id, ahora)
        db.session.flush()
        raise RuntimeError('fallo tras actualizar estadísticas')
    monkeypatch.setattr('gastronomia.services.sugerencias.tarea.actualizar', fallar)
    with pytest.raises(RuntimeError, match='tras actualizar'):
        recalcular(cliente)
    e = Estadistica.query.one()
    assert (e.mostradas, e.vendidas) == (77, 11)


@pytest.mark.parametrize('tabla', ['gastronomia_sugerencias_pedido', 'gastronomia_sugerencias_estadistica'])
def test_error_sql_no_impide_guardar_cocina_cobrar_ni_stock(pantalla, tabla):
    app, client, cliente, ids = pantalla
    activar(pantalla)
    _abrir_caja(app, 'admin_sugerencias')
    with app.app_context():
        producto = db.session.get(GastronomiaProducto, ids[0])
        producto.control_stock_venta = True
        producto.stock_disponible = 10
        db.session.commit()
    html = client.get('/gastronomia/pos').get_data(as_text=True)
    token = re.search(r'id="csrf-token" value="([^"]+)"', html).group(1)
    headers = {'X-CSRFToken': token}
    def fallar(conn, cursor, statement, *args):
        if statement.lower().startswith(f'insert into {tabla}'):
            cursor.execute('INSERT INTO tabla_inexistente_qa_sugerencias VALUES (1)')
    with app.app_context():
        motor = db.engine
    event.listen(motor, 'before_cursor_execute', fallar)
    try:
        resp = client.post('/api/gastronomia/pedidos', json=payload(ids), headers=headers)
        assert resp.status_code == 201
        pid = resp.get_json()['pedido']['id_pedido']
        assert client.post(f'/api/gastronomia/pedidos/{pid}/enviar-cocina', json={}, headers=headers).status_code == 200
        resp = client.post(f'/api/gastronomia/caja/pedidos/{pid}/cobrar', json={'metodo_pago': 'efectivo'}, headers=headers)
        assert resp.status_code == 200
    finally:
        event.remove(motor, 'before_cursor_execute', fallar)
    with app.app_context():
        assert Exposicion.query.filter_by(cliente_id=cliente).count() == 0
        assert GastronomiaPedidoPago.query.filter_by(cliente_id=cliente, pedido_id=pid).one().id_venta
        assert float(db.session.get(GastronomiaProducto, ids[0]).stock_disponible) == 9


def test_api_edicion_restauracion_y_escape_en_tarjeta(pantalla):
    app, client, cliente, ids = pantalla
    activar(pantalla)
    html = client.get('/gastronomia/pos').get_data(as_text=True)
    headers = {'X-CSRFToken': re.search(r'id="csrf-token" value="([^"]+)"', html).group(1)}
    data = payload(ids)
    resp = client.post('/api/gastronomia/pedidos', json=data, headers=headers)
    assert resp.status_code == 201
    pid = resp.get_json()['pedido']['id_pedido']
    assert resp.get_json()['pedido']['items'][1]['origen_sugerencia'] == ids[0]
    for _ in range(2):
        assert client.put(f'/api/gastronomia/pedidos/{pid}', json=data, headers=headers).status_code == 200
    restaurado = client.get(f'/api/gastronomia/pedidos/{pid}').get_json()['pedido']
    assert restaurado['sugerencias']['mostradas'] == [ids[:2]]
    assert restaurado['items'][1]['origen_sugerencia'] == ids[0]
    with app.app_context():
        assert Estadistica.query.filter_by(cliente_id=cliente).one().mostradas == 1
        e = Estadistica.query.filter_by(cliente_id=cliente).one()
        e.mostradas = 10
        e.resueltas = 10
        db.session.commit()
        from flask import render_template
        card = render_template('inteligencia/gastronomia/_sugerencias.html',
                               panel={'gastronomia': {'sugerencias': resumen(cliente, periodo())}})
        assert 'Papas &lt;script&gt;' in card
        assert 'Papas <script>' not in card


def test_edicion_con_error_estadistico_no_reutiliza_marcas_anteriores(pantalla):
    app, client, cliente, ids = pantalla
    activar(pantalla)
    html = client.get('/gastronomia/pos').get_data(as_text=True)
    headers = {'X-CSRFToken': re.search(r'id="csrf-token" value="([^"]+)"', html).group(1)}
    data = payload(ids)
    resp = client.post('/api/gastronomia/pedidos', json=data, headers=headers)
    pid = resp.get_json()['pedido']['id_pedido']
    with app.app_context():
        motor = db.engine
    def fallar(conn, cursor, statement, *args):
        if statement.lower().startswith('update gastronomia_sugerencias_pedido'):
            cursor.execute('INSERT INTO tabla_inexistente_qa_sugerencias VALUES (1)')
    event.listen(motor, 'before_cursor_execute', fallar)
    try:
        resp = client.put(f'/api/gastronomia/pedidos/{pid}', json=payload(ids, False), headers=headers)
        assert resp.status_code == 200
        assert not any(i.get('origen_sugerencia') for i in resp.get_json()['pedido']['items'])
    finally:
        event.remove(motor, 'before_cursor_execute', fallar)
