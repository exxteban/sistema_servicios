from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app import db
from app.models import Caja, Cliente, SesionCaja, Venta
from gastronomia.models import GastronomiaProducto as Producto
from gastronomia.channel_models import GastronomiaProductoPrecioCanal as Precio
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaConfig as Config, GastronomiaSugerenciaPar as Par,
    GastronomiaSugerenciaOrigen as Origen, GastronomiaSugerenciaPedido as Exposicion,
    GastronomiaSugerenciaEstadistica as Estadistica,
)
from gastronomia.services.sugerencias.consulta_pos import consultar
from gastronomia.services.sugerencias.diagnostico_pos import medir_pos, cobertura_registrada, _tiempos
from test_gastronomia_sugerencias import datos, pedido  # noqa: F401


def preparar(datos):
    cliente, _, ids = datos
    db.session.add(Config(cliente_id=cliente, activo=True, mostrar_en_pos=True, max_franja=2))
    db.session.add(Origen(cliente_id=cliente, id_origen=ids[0], pedidos=12))
    db.session.add(Par(cliente_id=cliente, id_origen=ids[0], id_destino=ids[1],
                       soporte=4, confianza=.5, lift=2, puntaje=.3))
    db.session.commit()
    return cliente, ids


def test_cobertura_aplica_filtros_sin_escribir(datos):
    cliente, ids = preparar(datos)
    escrituras = []
    def vigilar(conn, cursor, statement, *args):
        if statement.lstrip().split()[0].lower() in {'insert', 'update', 'delete', 'create', 'alter'}:
            escrituras.append(statement)
    event.listen(db.engine, 'before_cursor_execute', vigilar)
    try:
        resultado = medir_pos(cliente, {ids[0]: 12, ids[1]: 5}, repeticiones=2)
    finally:
        event.remove(db.engine, 'before_cursor_execute', vigilar)
    assert resultado['consultas'] == 4
    assert resultado['consultas_con_sugerencias'] == 2
    assert resultado['cobertura_muestra_porcentaje'] == 50
    assert resultado['productos'][0]['id_producto'] == ids[0]
    assert resultado['productos'][0]['sugerencias_por_consulta'] == [1, 1]
    assert resultado['estados'] == {'ok': 4}
    assert resultado['maximo_ms'] >= resultado['mediana_ms'] >= resultado['minimo_ms'] >= 0
    assert not escrituras and not db.session.new and not db.session.dirty
    p = db.session.get(Producto, ids[1])
    p.control_stock_venta, p.stock_disponible = True, 0
    db.session.commit()
    assert medir_pos(cliente, {ids[0]: 12}, repeticiones=1)['cobertura_muestra_porcentaje'] == 0


def test_canal_fatiga_y_config_actual(datos):
    cliente, ids = preparar(datos)
    db.session.add(Precio(cliente_id=cliente, producto_id=ids[1], canal='pedidosya', precio=50))
    db.session.commit()
    assert medir_pos(cliente, {ids[0]: 12}, repeticiones=1)['consultas_con_sugerencias'] == 1
    assert medir_pos(cliente, {ids[0]: 12}, repeticiones=1, canal_precio='pedidosya')['consultas_con_sugerencias'] == 0
    db.session.add(Estadistica(cliente_id=cliente, id_origen=ids[0], id_destino=ids[1],
                              oculto_hasta=datetime.utcnow() + timedelta(days=30)))
    db.session.commit()
    assert medir_pos(cliente, {ids[0]: 12}, repeticiones=1)['consultas_con_sugerencias'] == 0
    Config.query.one().mostrar_en_pos = False
    db.session.commit()
    r = medir_pos(cliente, {ids[0]: 12}, repeticiones=1)
    assert r['configuracion'] == {'activo': False, 'max': 0}
    assert r['estados'] == {'desactivado': 1}


def test_vacio_sin_historial_y_aislamiento(datos):
    cliente, ids = preparar(datos)
    otro = Cliente(nombre='Otro diagnóstico', ruc_ci='otro-diag-pos')
    db.session.add(otro)
    db.session.commit()
    assert medir_pos(cliente, {}, repeticiones=1)['cobertura_muestra_porcentaje'] is None
    assert medir_pos(otro.id_cliente, {ids[0]: 12}, repeticiones=1)['origenes_evaluados'] == 0
    p = db.session.get(Producto, ids[0])
    p.visible = False
    db.session.commit()
    assert medir_pos(cliente, {ids[0]: 12}, repeticiones=1)['origenes_evaluados'] == 0


def test_tope_errores_y_tiempos_no_parecen_sugerencias(datos, monkeypatch):
    cliente, ids = preparar(datos)
    def lento(*args, **kwargs):
        raise TimeoutError('tope')
    monkeypatch.setattr('gastronomia.services.sugerencias.consulta_pos.previsualizar', lento)
    r = medir_pos(cliente, {ids[0]: 12}, repeticiones=1)
    assert r['estados'] == {'tiempo_agotado': 1} and r['consultas_con_sugerencias'] == 0
    def fallar(*args, **kwargs):
        raise OperationalError('dato privado', {}, Exception('no publicar'))
    monkeypatch.setattr('gastronomia.services.sugerencias.consulta_pos.previsualizar', fallar)
    r = medir_pos(cliente, {ids[0]: 12}, repeticiones=1)
    assert r['estados'] == {'error:OperationalError': 1}
    assert 'privado' not in json.dumps(r) and 'no publicar' not in json.dumps(r)
    assert _tiempos([10, 1, 3, 2, 4]) == dict(minimo_ms=1, mediana_ms=3, p95_ms=10, maximo_ms=10)


def test_respuesta_tardia_del_servicio_se_descarta(datos, monkeypatch):
    cliente, ids = preparar(datos)
    reloj = iter([0, 0, 1])
    monkeypatch.setattr('gastronomia.services.sugerencias.consulta_pos.monotonic', lambda: next(reloj))
    monkeypatch.setattr('gastronomia.services.sugerencias.consulta_pos.previsualizar', lambda *a, **k: {
        'sugerencias': [dict(id_producto=ids[1], id_origen=ids[0], fuente='producto', motivo='Juntos')],
    })
    r = consultar(cliente, [ids[0]])
    assert r['estado'] == 'tiempo_agotado' and r['sugerencias'] == []


def test_exposicion_real_deduplica_y_excluye_no_cobrados_anulados_y_tienda(datos):
    cliente, usuario, ids = datos
    p = pedido(datos, ids[:2])
    for origen, destino in [(ids[0], ids[1]), (ids[1], ids[0])]:
        db.session.add(Exposicion(cliente_id=cliente, pedido_id=p.id_pedido, id_origen=origen, producto_id=destino))
    pedido(datos, ids[:1])  # segundo pedido POS cobrado sin exposición
    pedido(datos, ids[:1], pagado=False)
    pedido(datos, ids[:1], encargo=True)
    tienda = pedido(datos, ids[:1])
    tienda.origen_pedido = 'tienda_online'
    db.session.commit()
    r = cobertura_registrada(cliente, datetime.utcnow())
    assert (r['pedidos_pos_cobrados'], r['pedidos_con_exposicion'], r['porcentaje']) == (2, 1, 50)
    caja = Caja(nombre='Diagnóstico')
    db.session.add(caja)
    db.session.flush()
    sesion = SesionCaja(id_caja=caja.id_caja, id_usuario=usuario)
    db.session.add(sesion)
    db.session.flush()
    venta = Venta(id_cliente=cliente, id_sesion_caja=sesion.id_sesion, subtotal=20, total=20, estado='anulada')
    db.session.add(venta)
    db.session.flush()
    p.pago.id_venta = venta.id_venta
    db.session.commit()
    r = cobertura_registrada(cliente, datetime.utcnow())
    assert (r['pedidos_pos_cobrados'], r['pedidos_con_exposicion'], r['porcentaje']) == (1, 0, 0)


@pytest.mark.parametrize('campo,valor', [('muestra', 0), ('muestra', 101), ('repeticiones', 0), ('repeticiones', 6)])
def test_limites_de_consultas(datos, campo, valor):
    with pytest.raises(ValueError):
        medir_pos(datos[0], {}, **{campo: valor})


def ejecutar_cli(archivo, *opciones):
    return subprocess.run([sys.executable, 'scripts/diagnostico_sugerencias_gastronomia.py',
                           '--sqlite', str(archivo), *opciones],
                          cwd=Path(__file__).resolve().parent, capture_output=True, text=True,
                          encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, timeout=30)


def test_cli_no_crea_base_ni_tablas(tmp_path):
    inexistente = tmp_path / 'no-existe.db'
    assert ejecutar_cli(inexistente).returncode != 0
    assert not inexistente.exists()
    archivo = tmp_path / 'incompleta.db'
    with sqlite3.connect(archivo) as conn:
        conn.execute('CREATE TABLE sentinela (id INTEGER)')
    antes = hashlib.sha256(archivo.read_bytes()).hexdigest()
    proceso = ejecutar_cli(archivo)
    assert proceso.returncode != 0
    r = json.loads(proceso.stdout)
    assert r['estado'] == 'esquema_pendiente'
    assert hashlib.sha256(archivo.read_bytes()).hexdigest() == antes


@pytest.mark.parametrize('datos', ['archivo'], indirect=True)
def test_cli_completo_con_base_existente_es_solo_lectura(datos):
    cliente, ids = preparar(datos)
    pedido(datos, ids[:2])
    archivo = Path(db.engine.url.database)
    db.session.remove()
    antes = hashlib.sha256(archivo.read_bytes()).hexdigest()
    proceso = ejecutar_cli(archivo, '--cliente-id', str(cliente), '--muestra-pos', '1',
                          '--repeticiones-pos', '1', '--canal', 'todos')
    assert proceso.returncode == 0, proceso.stderr + proceso.stdout
    r = json.loads(proceso.stdout)
    assert [c['canal_precio'] for c in r['consulta_pos']] == ['normal', 'pedidosya', 'monchis']
    assert r['consulta_pos'][0]['consultas_con_sugerencias'] == 1
    assert r['cobertura_registrada']['pedidos_pos_cobrados'] == 1
    assert hashlib.sha256(archivo.read_bytes()).hexdigest() == antes
