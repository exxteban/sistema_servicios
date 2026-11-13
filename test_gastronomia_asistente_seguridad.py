"""Garantias de seguridad del asistente IA de configuracion gastronomica.

Nada se guarda sin que el usuario confirme, se respetan permisos, las propuestas son de un solo uso,
y un nombre parecido nunca hace que se modifique otro plato o insumo.
"""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from app import create_app, db
from app.models import Producto
from app.models.producto import Categoria
from app.models.usuario import Usuario
from gastronomia.asistente_models import GastronomiaAsistentePropuesta
from gastronomia.models import GastronomiaMesa, GastronomiaProducto
from gastronomia.services.asistente import motor, propuestas
from gastronomia.services.asistente.vista_previa import Pendientes
from gastronomia.services.permisos import PERMISO_SALON
from test_gastronomia_asistente_ia import _FakeClient, _tool, _tool_call
from test_gastronomia_menu import _crear_restaurante, _csrf, _loguear


def _cfg(monkeypatch, respuestas):
    fake = _FakeClient(respuestas)
    monkeypatch.setattr(motor, '_crear_cliente', lambda *a: (fake, 'test'))
    monkeypatch.setattr(motor, 'obtener_configuracion_asistente', lambda: SimpleNamespace(
        enabled=True, provider='deepseek', model='m', deepseek_base_url='', max_tokens=700, temperature=0.2,
    ))
    monkeypatch.setattr(motor, 'replace', lambda cfg, **kw: SimpleNamespace(**{**vars(cfg), **kw}))
    monkeypatch.setattr(motor, 'validar_presupuesto_tokens', lambda *a, **k: (True, 'ok'))
    return fake


def _respuesta_tools(*llamadas):
    return SimpleNamespace(content='', tool_calls=[_tool_call(n, a) for n, a in llamadas], model_extra={})


def _final(texto='Revisa y confirma.'):
    return SimpleNamespace(content=texto, tool_calls=None, model_extra={})


def _base(app, cliente_id):
    with app.app_context():
        _tool('crear_categorias', {'categorias': [{'nombre': 'Pizzas'}]}, cliente_id)
        _tool('guardar_platos', {'platos': [
            {'nombre': 'Pizza napolitana', 'categoria': 'Pizzas', 'precio': 50000},
            {'nombre': 'Muzza', 'categoria': 'Pizzas', 'precio': 45000},
        ]}, cliente_id)


def _precio(cliente_id, nombre):
    return float(GastronomiaProducto.query.filter_by(cliente_id=cliente_id, nombre=nombre).one().precio)


def test_escrituras_no_usan_nombres_parciales_ni_ids_equivocados():
    app = create_app('testing')
    cliente_id = _crear_restaurante(app, 'Resto Seg1', 'resto_seg1')
    _base(app, cliente_id)
    with app.app_context():
        from gastronomia.services.asistente.motor import ejecutar_tool

        # "pizza" es parcial de un solo plato: leer lo acepta, escribir NO (podria ser otro plato).
        assert _tool('ver_plato', {'plato': 'pizza'}, cliente_id)['nombre'] == 'Pizza napolitana'
        cambio = ejecutar_tool('cambiar_estado_plato', {'plato': 'pizza', 'precio': 1}, cliente_id, None)
        assert not cambio['ok'] and 'Pizza napolitana' in cambio['error']
        assert _precio(cliente_id, 'Pizza napolitana') == 50000

        # Un id que no corresponde al nombre no renombra ni pisa otro plato.
        muzza = GastronomiaProducto.query.filter_by(cliente_id=cliente_id, nombre='Muzza').one()
        mal = _tool('guardar_platos', {'platos': [{'id_producto': muzza.id_producto, 'nombre': 'Fugazza', 'precio': 1}]}, cliente_id)
        assert mal['hechos'] == [] and 'nuevo_nombre' in mal['errores'][0]['error']
        assert _precio(cliente_id, 'Muzza') == 45000

        ok = _tool('guardar_platos', {'platos': [{'id_producto': muzza.id_producto, 'nuevo_nombre': 'Muzzarella'}]}, cliente_id)
        assert ok['hechos'][0]['nombre'] == 'Muzzarella' and _precio(cliente_id, 'Muzzarella') == 45000

        # Receta con un insumo parecido pero no exacto: no se vincula otro insumo.
        _tool('guardar_insumos', {'insumos': [{'nombre': 'Queso muzzarella', 'unidad': 'g', 'precio_compra': 50}]}, cliente_id)
        receta = _tool('guardar_receta_plato', {'plato': 'Muzzarella', 'ingredientes': [{'insumo': 'queso', 'cantidad': 100}]}, cliente_id)
        assert receta['faltantes'] == ['queso']


def test_chat_solo_propone_y_vista_previa_no_escribe(monkeypatch):
    app = create_app('testing')
    cliente_id = _crear_restaurante(app, 'Resto Seg2', 'resto_seg2')
    _base(app, cliente_id)
    _cfg(monkeypatch, [
        _respuesta_tools(
            ('cambiar_estado_plato', {'plato': 'Muzza', 'precio': 47000, 'disponible': False}),
            ('crear_categorias', {'categorias': [{'nombre': 'Burgers'}]}),
            ('guardar_platos', {'platos': [{'nombre': 'Clasica', 'categoria': 'Burgers', 'precio': 30000}]}),
            ('guardar_insumos', {'insumos': [{'nombre': 'Carne', 'unidad': 'g', 'precio_compra': 60}]}),
            ('guardar_receta_plato', {'plato': 'Clasica', 'ingredientes': [{'insumo': 'Carne', 'cantidad': 150}]}),
            ('configurar_extras_plato', {'plato': 'Clasica', 'adicionales': [{'nombre': 'Bacon', 'precio': 5000}]}),
            ('crear_mesas', {'cantidad': 3}),
        ),
        _final(),
    ])
    client = app.test_client()
    _loguear(client, app, 'resto_seg2')
    headers = {'X-CSRFToken': _csrf(client.get('/gastronomia/menu').get_data(as_text=True))}
    data = client.post('/gastronomia/asistente/api/chat', headers=headers, json={'mensaje': 'carga todo'}).get_json()
    resumen = data['propuesta']['resumen']
    assert "Plato 'Muzza': precio 45.000 -> 47.000; disponible si -> no" in resumen
    assert "Receta de 'Clasica' quedaria: Carne 150 g" in resumen
    assert "Adicionales de 'Clasica' quedarian: Bacon +5.000" in resumen
    assert 'Crear 3 mesa(s): Mesa 1 a Mesa 3 (capacidad 4)' in resumen
    with app.app_context():
        assert _precio(cliente_id, 'Muzza') == 45000
        assert GastronomiaProducto.query.filter_by(cliente_id=cliente_id, nombre='Clasica').count() == 0
        assert Producto.query.filter_by(nombre='Carne').count() == 0
        assert GastronomiaMesa.query.filter_by(cliente_id=cliente_id).count() == 0

    confirmado = client.post(f"/gastronomia/asistente/api/propuesta/{data['propuesta']['id']}/confirmar", headers=headers).get_json()
    assert confirmado['ok'] and 'Con problemas' not in confirmado['mensaje'], confirmado
    with app.app_context():
        assert _precio(cliente_id, 'Muzza') == 47000
        assert GastronomiaMesa.query.filter_by(cliente_id=cliente_id).count() == 3
        detalle = _tool('ver_plato', {'plato': 'Clasica'}, cliente_id)
        assert detalle['receta'][0]['insumo'] == 'Carne' and detalle['grupos_opciones'][0]['opciones'][0]['nombre'] == 'Bacon'


def test_permisos_se_verifican_al_proponer_y_al_confirmar(monkeypatch):
    app = create_app('testing')
    cliente_id = _crear_restaurante(app, 'Resto Seg3', 'resto_seg3')
    fake = _cfg(monkeypatch, [_respuesta_tools(('crear_mesas', {'cantidad': 2})), _final('No tenes permiso.')])
    enviados = []
    original = fake._create
    fake.chat.completions.create = lambda **kw: (enviados.append(list(kw['messages'])), original(**kw))[1]
    sin_salon = lambda *codigos: PERMISO_SALON not in codigos  # noqa: E731
    monkeypatch.setattr(propuestas, 'tiene_permiso_gastronomia', sin_salon)

    client = app.test_client()
    _loguear(client, app, 'resto_seg3')
    headers = {'X-CSRFToken': _csrf(client.get('/gastronomia/menu').get_data(as_text=True))}
    data = client.post('/gastronomia/asistente/api/chat', headers=headers, json={'mensaje': 'crea 2 mesas'}).get_json()
    assert data['propuesta'] is None
    assert 'permiso' in json.loads(enviados[1][-1]['content'])['error']

    # Propuesta armada con permiso, pero al confirmar ya no lo tiene: no se ejecuta.
    with app.app_context():
        usuario_id = Usuario.query.filter_by(username='resto_seg3').one().id_usuario
        accion = {'tool': 'crear_mesas', 'args': {'cantidad': 2}, 'resumen': ['Crear 2 mesas']}
        propuesta = propuestas.crear(cliente_id, usuario_id, [accion])
    resultado = client.post(f"/gastronomia/asistente/api/propuesta/{propuesta['id']}/confirmar", headers=headers).get_json()
    assert resultado['hubo_cambios'] is False and 'sin permiso' in resultado['mensaje']
    with app.app_context():
        assert GastronomiaMesa.query.filter_by(cliente_id=cliente_id).count() == 0


def test_propuesta_es_de_un_usuario_un_solo_uso_y_vence(monkeypatch):
    app = create_app('testing')
    cliente_id = _crear_restaurante(app, 'Resto Seg4', 'resto_seg4')
    otro_cliente = _crear_restaurante(app, 'Resto Seg4b', 'resto_seg4b')
    _base(app, cliente_id)
    monkeypatch.setattr(propuestas, 'tiene_permiso_gastronomia', lambda *a: True)
    accion = {'tool': 'cambiar_estado_plato', 'args': {'plato': 'Muzza', 'precio': 1}, 'resumen': ['x']}
    with app.test_request_context():
        usuario_id = Usuario.query.filter_by(username='resto_seg4').one().id_usuario
        otro_usuario = Usuario.query.filter_by(username='resto_seg4b').one().id_usuario

        p1 = propuestas.crear(cliente_id, usuario_id, [accion])
        # Otro usuario u otro local no pueden confirmarla.
        assert not propuestas.confirmar(cliente_id, otro_usuario, p1['id'])['ok']
        assert not propuestas.confirmar(otro_cliente, usuario_id, p1['id'])['ok']
        # Una propuesta nueva reemplaza a la anterior: la vieja ya no se puede ejecutar.
        p2 = propuestas.crear(cliente_id, usuario_id, [accion])
        assert not propuestas.confirmar(cliente_id, usuario_id, p1['id'])['ok']
        # Vencida (mas de 30 minutos): no se ejecuta.
        fila = db.session.get(GastronomiaAsistentePropuesta, p2['id'])
        fila.fecha_creacion = datetime.utcnow() - timedelta(minutes=31)
        db.session.commit()
        assert propuestas.vigente(cliente_id, usuario_id) is None
        assert not propuestas.confirmar(cliente_id, usuario_id, p2['id'])['ok']
        # Cancelada: tampoco.
        p3 = propuestas.crear(cliente_id, usuario_id, [accion])
        assert propuestas.cancelar(cliente_id, usuario_id, p3['id'])['ok']
        assert not propuestas.confirmar(cliente_id, usuario_id, p3['id'])['ok']
        assert _precio(cliente_id, 'Muzza') == 45000


def test_vista_previa_avisa_y_rechaza_antes_de_proponer(monkeypatch):
    app = create_app('testing')
    cliente_id = _crear_restaurante(app, 'Resto Seg5', 'resto_seg5')
    _base(app, cliente_id)
    monkeypatch.setattr(propuestas, 'tiene_permiso_gastronomia', lambda *a: True)
    with app.test_request_context():
        cat = Categoria(nombre='Bebidas general', activo=True)
        db.session.add(cat)
        db.session.flush()
        db.session.add(Producto(codigo='GEN-1', nombre='Coca general', id_categoria=cat.id_categoria, id_cliente=None,
                                precio_compra=5000, precio_venta=8000, stock_actual=0, stock_minimo=0, activo=True))
        db.session.commit()

        acciones = []
        aviso = propuestas.preparar('guardar_insumos', {'insumos': [{'nombre': 'Coca general', 'precio_compra': 6000}]},
                                    cliente_id, Pendientes(), acciones)
        assert 'inventario general' in aviso['data']['resumen'][0]

        error = propuestas.preparar('guardar_platos', {'platos': [{'nombre': 'Nuevo', 'categoria': 'No existe'}]},
                                    cliente_id, Pendientes(), acciones)
        assert not error['ok'] and 'categoria' in error['error']
        vacia = propuestas.preparar('guardar_receta_plato', {'plato': 'Muzza', 'modo': 'reemplazar', 'ingredientes': []},
                                    cliente_id, Pendientes(), acciones)
        assert 'VACIA' in vacia['data']['resumen'][0]
        assert len(acciones) == 2
        assert float(Producto.query.filter_by(codigo='GEN-1').one().precio_compra) == 5000


def test_limpiar_cancela_la_propuesta_pendiente(monkeypatch):
    app = create_app('testing')
    cliente_id = _crear_restaurante(app, 'Resto Seg6', 'resto_seg6')
    _base(app, cliente_id)
    _cfg(monkeypatch, [_respuesta_tools(('cambiar_estado_plato', {'plato': 'Muzza', 'precio': 1})), _final()])
    client = app.test_client()
    _loguear(client, app, 'resto_seg6')
    headers = {'X-CSRFToken': _csrf(client.get('/gastronomia/menu').get_data(as_text=True))}
    data = client.post('/gastronomia/asistente/api/chat', headers=headers, json={'mensaje': 'muzza a 1'}).get_json()
    client.post('/gastronomia/asistente/api/limpiar', headers=headers)
    url = f"/gastronomia/asistente/api/propuesta/{data['propuesta']['id']}/confirmar"
    assert client.post(url, headers=headers).status_code == 409
    with app.app_context():
        assert _precio(cliente_id, 'Muzza') == 45000
