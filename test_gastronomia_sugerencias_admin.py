import re
from datetime import datetime

import pytest

from app import create_app, db
from app.models import Cliente, Configuracion, Usuario
from gastronomia.models import GastronomiaCategoria, GastronomiaProducto
from gastronomia.services.sugerencias import reglas
from gastronomia.services.sugerencias.candidatos import previsualizar
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaRegla as Regla, GastronomiaSugerenciaExcluido as Excluido,
    GastronomiaSugerenciaConfig as Config, GastronomiaSugerenciaPar as Par,
    GastronomiaSugerenciaOrigen as Origen, GastronomiaSugerenciaCalculo as Estado,
)
from test_gastronomia_sugerencias import datos  # noqa: F401
from test_gastronomia_menu import _crear_restaurante, _loguear


def regla(datos, **cambios):
    _, _, ids = datos
    return dict(tipo='forzar', origen=f'producto:{ids[0]}', destino=f'producto:{ids[1]}', **cambios)


def test_reglas_edicion_prohibicion_y_pausa(datos):
    cliente, usuario, ids = datos
    data = regla(datos)
    reglas.guardar_regla(cliente, usuario, data)
    assert previsualizar(cliente, [ids[0]])['sugerencias'][0]['id_producto'] == ids[1]
    data['tipo'] = 'prohibir'
    reglas.guardar_regla(cliente, usuario, data)
    assert Regla.query.count() == 1
    assert previsualizar(cliente, [ids[0]])['sugerencias'] == []
    data['tipo'] = 'forzar'
    reglas.guardar_regla(cliente, usuario, data)
    fila = Regla.query.one()
    reglas.cambiar_regla(cliente, fila.id, 'alternar')
    assert previsualizar(cliente, [ids[0]])['sugerencias'] == []
    reglas.cambiar_regla(cliente, fila.id, 'alternar')
    data['destino'] = f'producto:{ids[2]}'
    reglas.guardar_regla(cliente, usuario, data, fila.id)
    assert previsualizar(cliente, [ids[0]])['sugerencias'][0]['id_producto'] == ids[2]


def test_referencias_y_operaciones_no_cruzan_clientes(datos):
    cliente, usuario, ids = datos
    otro = Cliente(nombre='Otro', ruc_ci='admin-otro')
    db.session.add(otro)
    db.session.flush()
    categoria = GastronomiaCategoria(cliente_id=otro.id_cliente, nombre='Otra')
    db.session.add(categoria)
    db.session.commit()
    with pytest.raises(ValueError):
        reglas.excluir(cliente, f'categoria:{categoria.id_categoria}')
    reglas.guardar_regla(cliente, usuario, regla(datos))
    fila = Regla.query.one()
    with pytest.raises(ValueError):
        reglas.cambiar_regla(otro.id_cliente, fila.id, 'eliminar')
    with pytest.raises(ValueError):
        reglas.guardar_regla(otro.id_cliente, usuario, regla(datos), fila.id)
    assert Regla.query.count() == 1
    assert previsualizar(otro.id_cliente, [ids[0]])['sugerencias'] == []


@pytest.mark.parametrize('campo,valor', [('disponible', False), ('activo', False), ('visible', False), ('stock_disponible', 0)])
def test_forzar_respeta_disponibilidad_y_carrito(datos, campo, valor):
    cliente, usuario, ids = datos
    reglas.guardar_regla(cliente, usuario, regla(datos))
    p = db.session.get(GastronomiaProducto, ids[1])
    p.control_stock_venta = campo == 'stock_disponible'
    setattr(p, campo, valor)
    db.session.commit()
    resultado = previsualizar(cliente, [ids[0]])
    assert resultado['sugerencias'] == []
    assert resultado['descartados']


def test_exclusion_y_prohibicion_categoria_ganan_a_regla(datos):
    cliente, usuario, ids = datos
    reglas.guardar_regla(cliente, usuario, regla(datos))
    assert previsualizar(cliente, ids[:2])['sugerencias'] == []
    reglas.excluir(cliente, f'producto:{ids[1]}')
    reglas.excluir(cliente, f'producto:{ids[1]}')
    assert Excluido.query.count() == 1
    assert previsualizar(cliente, [ids[0]])['descartados'][0]['descarte'] == 'Excluido por el negocio'
    reglas.quitar_exclusion(cliente, Excluido.query.one().id)
    categoria_id = db.session.get(GastronomiaProducto, ids[1]).categoria_id
    reglas.guardar_regla(cliente, usuario, dict(tipo='prohibir', origen='cualquiera', destino=f'categoria:{categoria_id}'))
    assert previsualizar(cliente, [ids[0]])['descartados'][0]['descarte'] == 'Combinación prohibida'


@pytest.mark.parametrize('tipo', ['producto', 'categoria'])
@pytest.mark.parametrize('antiguo,excluido', [(False, False), (True, False), (False, True)])
def test_prohibicion_respeta_todo_el_carrito(datos, tipo, antiguo, excluido):
    cliente, _, ids = datos
    categoria = GastronomiaCategoria(cliente_id=cliente, nombre='Origen prohibido')
    db.session.add(categoria)
    db.session.flush()
    db.session.get(GastronomiaProducto, ids[0]).categoria_id = categoria.id_categoria
    db.session.add_all([
        Regla(cliente_id=cliente, tipo='prohibir', origen_tipo=tipo,
              origen_id=ids[0] if tipo == 'producto' else categoria.id_categoria,
              destino_tipo='producto', destino_id=ids[2]),
        Regla(cliente_id=cliente, tipo='forzar', origen_tipo='producto', origen_id=ids[1],
              destino_tipo='producto', destino_id=ids[2]),
    ])
    if excluido:
        db.session.add(Excluido(cliente_id=cliente, tipo='producto', id_ref=ids[0]))
    db.session.commit()
    # La regla positiva sigue funcionando cuando falta el producto prohibido.
    assert previsualizar(cliente, [ids[1]])['sugerencias'][0]['id_producto'] == ids[2]
    carrito = [ids[0], ids[3], ids[4], ids[1]] if antiguo else ids[:2]
    resultado = previsualizar(cliente, carrito)
    assert resultado['sugerencias'] == []
    assert resultado['descartados'][0]['descarte'] == 'Combinación prohibida'


def test_config_valida_y_no_se_crea_en_lectura(datos):
    cliente = datos[0]
    previsualizar(cliente, [datos[2][0]])
    assert Config.query.count() == 0
    with pytest.raises(ValueError):
        reglas.guardar_config(cliente, dict(max_franja='4'))
    reglas.guardar_config(cliente, dict(activo='1', max_franja='2'))
    assert Config.query.one().activo is True
    assert Config.query.one().mostrar_en_pos is False


def test_preview_asociaciones_y_precio(datos):
    cliente, _, ids = datos
    db.session.add(Origen(cliente_id=cliente, nivel='producto', id_origen=ids[0], pedidos=12))
    db.session.add(Par(cliente_id=cliente, nivel='producto', id_origen=ids[0], id_destino=ids[1],
                       soporte=6, confianza=.5, lift=2, puntaje=.3))
    db.session.commit()
    assert previsualizar(cliente, [ids[0]])['sugerencias'][0]['soporte'] == 6
    db.session.get(GastronomiaProducto, ids[1]).precio = 100
    db.session.commit()
    assert previsualizar(cliente, [ids[0]])['descartados'][0]['descarte'].startswith('Precio')


def test_categoria_con_poco_historial_y_prioridad(datos):
    cliente, usuario, ids = datos
    origen = db.session.get(GastronomiaProducto, ids[0])
    categoria = GastronomiaCategoria(cliente_id=cliente, nombre='Bebidas')
    db.session.add(categoria)
    db.session.flush()
    db.session.get(GastronomiaProducto, ids[1]).categoria_id = categoria.id_categoria
    db.session.add(Par(cliente_id=cliente, nivel='categoria', id_origen=origen.categoria_id,
                       id_destino=categoria.id_categoria, soporte=8, confianza=.5, lift=2, puntaje=.3))
    db.session.commit()
    assert previsualizar(cliente, [ids[0]])['sugerencias'][0]['fuente'] == 'categoria'
    reglas.guardar_regla(cliente, usuario, dict(tipo='forzar', origen='cualquiera',
                                               destino=f'producto:{ids[2]}', prioridad='1'))
    assert previsualizar(cliente, [ids[0]])['sugerencias'][0]['id_producto'] == ids[2]


def test_recalculo_manual_evitar_hilos_duplicados_y_recuperar_error(monkeypatch):
    from flask import Flask
    from gastronomia.services.sugerencias import recalculo_manual as manual
    app = Flask(__name__)
    monkeypatch.setattr(manual, '_pendientes', set())
    hilos = []
    class Hilo:
        def __init__(self, **kwargs):
            hilos.append(kwargs)
        def start(self):
            pass
    monkeypatch.setattr(manual.threading, 'Thread', Hilo)
    assert manual.solicitar(app, 1)
    assert manual.solicitar(app, 1) is False
    assert len(hilos) == 1
    class HiloFallido(Hilo):
        def start(self):
            raise RuntimeError('sin recursos')
    monkeypatch.setattr(manual.threading, 'Thread', HiloFallido)
    with pytest.raises(RuntimeError):
        manual.solicitar(app, 2)
    assert 2 not in manual._pendientes


@pytest.fixture
def pantalla():
    app = create_app('testing')
    cliente = _crear_restaurante(app, 'Resto sugerencias', 'admin_sugerencias')
    with app.app_context():
        Configuracion.establecer('modo_operacion_principal', 'gastronomia')
        categoria = GastronomiaCategoria(cliente_id=cliente, nombre='Comidas')
        db.session.add(categoria)
        db.session.flush()
        productos = [GastronomiaProducto(cliente_id=cliente, categoria_id=categoria.id_categoria,
                                         nombre=n, precio=10000) for n in ('Hamburguesa', 'Papas <script>')]
        db.session.add_all(productos)
        db.session.add(Estado(cliente_id=cliente, fin=datetime.utcnow(), pedidos=10, pares=2))
        db.session.commit()
        ids = [p.id_producto for p in productos]
    client = app.test_client()
    _loguear(client, app, 'admin_sugerencias')
    return app, client, cliente, ids


def test_pantalla_guardado_csrf_y_preview(pantalla, monkeypatch):
    app, client, cliente, ids = pantalla
    url = '/gastronomia/sugerencias'
    page = client.get(url)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Último cálculo' in html
    assert 'Papas &lt;script&gt;' in html
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    data = dict(accion='regla', tipo='forzar', origen=f'producto:{ids[0]}', destino=f'producto:{ids[1]}')
    assert client.post(url, data=data).status_code == 302  # Manejador global de CSRF redirige.
    with app.app_context():
        assert Regla.query.filter_by(cliente_id=cliente).count() == 0
    data['csrf_token'] = token
    assert client.post(url, data=data).status_code == 302
    preview = client.get(url, query_string={'producto': f'producto:{ids[0]}'}).get_data(as_text=True)
    assert 'Regla del negocio' in preview and 'Nunca con este' in preview
    with app.app_context():
        assert Regla.query.filter_by(cliente_id=cliente).count() == 1
        assert Config.query.filter_by(cliente_id=cliente).count() == 0
    invocaciones = []
    monkeypatch.setattr('gastronomia.routes.sugerencias_routes.solicitar', lambda a, c: invocaciones.append(c) or True)
    assert client.post(url, data=dict(accion='recalcular', csrf_token=token)).status_code == 302
    assert invocaciones == [cliente]
    assert 'No hay reglas que coincidan' in client.get(url + '?q=inexistente').get_data(as_text=True)


def test_autenticacion_y_permiso_menu(pantalla):
    app, _, cliente, _ = pantalla
    anonimo = app.test_client()
    assert anonimo.get('/gastronomia/sugerencias').status_code == 302
    with app.app_context():
        usuario = Usuario(username='sin_menu_sugerencias', nombre_completo='Operador',
                          id_cliente=cliente, id_rol=3, password_hash='x')
        db.session.add(usuario)
        db.session.commit()
    _loguear(anonimo, app, 'sin_menu_sugerencias')
    assert anonimo.get('/gastronomia/sugerencias', headers={'Accept': 'application/json'}).status_code == 403
