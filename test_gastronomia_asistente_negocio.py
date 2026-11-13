"""El panel del asistente gastronomico suma las consultas de negocio del Asistente IA del topbar."""
from types import SimpleNamespace

from app import create_app
from gastronomia.services.asistente import consultas_negocio, motor, tools_ventas_local
from gastronomia.services.asistente.definiciones import TOOLS
from test_gastronomia_asistente_ia import _FakeClient, _tool_call
from test_gastronomia_menu import _crear_restaurante, _csrf, _loguear

NOMBRES_PANEL = {t['function']['name'] for t in TOOLS}


def _u(texto):
    return {'role': 'user', 'content': texto}


def test_selector_solo_suma_consultas_cuando_el_usuario_las_pide():
    create_app('testing')
    assert consultas_negocio.nombres_seleccionados([_u('ponele 150 g de carne a la clasica')]) == []
    # "donde / como cargo" lo resuelve donde_esta del panel, no la ayuda generica del backoffice.
    assert consultas_negocio.nombres_seleccionados([_u('donde esta la carga de mesas')]) == []
    ventas = consultas_negocio.nombres_seleccionados([_u('cuanto vendi esta semana?')])
    assert 'ventas_resumen_periodo' in ventas
    assert 'caja_estado_actual' in consultas_negocio.nombres_seleccionados([_u('como esta la caja')])
    assert not set(ventas) & NOMBRES_PANEL
    assert len(ventas) <= consultas_negocio.MAX_TOOLS_NEGOCIO
    # Las respuestas del asistente no rutean (hablan de categorias/productos todo el tiempo).
    historial = [_u('hola'), {'role': 'assistant', 'content': 'Te muestro las ventas y el stock de productos'}]
    assert consultas_negocio.nombres_seleccionados(historial) == []


def test_sin_permiso_de_asistente_ia_no_hay_consultas(monkeypatch):
    create_app('testing')
    monkeypatch.setattr(consultas_negocio, 'puede_usar_asistente_ia', lambda u: False)
    assert consultas_negocio.tools_para([_u('cuanto vendi hoy')], object()) == ([], set())


def _preparar(monkeypatch, fake):
    monkeypatch.setattr(motor, '_crear_cliente', lambda *a: (fake, 'test'))
    monkeypatch.setattr(motor, 'obtener_configuracion_asistente', lambda: SimpleNamespace(
        enabled=True, provider='deepseek', model='deepseek-v4-flash', deepseek_base_url='', max_tokens=700, temperature=0.2,
    ))
    monkeypatch.setattr(motor, 'replace', lambda cfg, **kw: SimpleNamespace(**{**vars(cfg), **kw}))
    monkeypatch.setattr(motor, 'validar_presupuesto_tokens', lambda *a, **k: (True, 'ok'))
    monkeypatch.setattr(consultas_negocio, 'puede_usar_asistente_ia', lambda u: True)


def test_panel_responde_consulta_de_ventas_con_tool_del_backoffice(monkeypatch):
    app = create_app('testing')
    _crear_restaurante(app, 'Resto Negocio', 'resto_negocio')
    enviados, ejecutadas = [], []
    fake = _FakeClient([
        SimpleNamespace(content='', tool_calls=[_tool_call('ventas_resumen_periodo', {'periodo': 'semana'})], model_extra={}),
        SimpleNamespace(content='Esta semana vendiste Gs. 1.000.000.', tool_calls=None, model_extra={}),
        SimpleNamespace(content='Listo.', tool_calls=None, model_extra={}),
    ])
    original = fake._create
    fake.chat.completions.create = lambda **kw: (enviados.append(kw), original(**kw))[1]
    _preparar(monkeypatch, fake)

    def _ejecutar(nombre, args, usuario=None):
        ejecutadas.append((nombre, args, getattr(usuario, 'username', None)))
        return {'ok': True, 'total': 1000000}

    monkeypatch.setattr(consultas_negocio, 'ejecutar_tool_backoffice', _ejecutar)

    client = app.test_client()
    _loguear(client, app, 'resto_negocio')
    headers = {'X-CSRFToken': _csrf(client.get('/gastronomia/menu').get_data(as_text=True))}
    data = client.post('/gastronomia/asistente/api/chat', headers=headers,
                       json={'mensaje': 'cuanto vendi esta semana?'}).get_json()

    assert data['mensaje'] == 'Esta semana vendiste Gs. 1.000.000.'
    assert data['propuesta'] is None and data['hubo_cambios'] is False
    assert ejecutadas[0][0] == 'ventas_resumen_periodo' and ejecutadas[0][2] == 'resto_negocio'
    nombres = {t['function']['name'] for t in enviados[0]['tools']}
    assert NOMBRES_PANEL <= nombres and 'ventas_resumen_periodo' in nombres
    assert 'Consultas del negocio' in enviados[0]['messages'][0]['content']
    assert '"total": 1000000' in enviados[1]['messages'][-1]['content']

    # Un pedido de configuracion manda exactamente lo mismo que antes de unificar.
    client.post('/gastronomia/asistente/api/limpiar', headers=headers)
    client.post('/gastronomia/asistente/api/chat', headers=headers, json={'mensaje': 'ponele 150 g de carne a la clasica'})
    assert {t['function']['name'] for t in enviados[2]['tools']} == NOMBRES_PANEL
    assert 'Consultas del negocio' not in enviados[2]['messages'][0]['content']


def test_ventas_por_plato_usan_reportes_de_gastronomia_no_productos_de_inventario():
    app = create_app('testing')
    cliente_id = _crear_restaurante(app, 'Resto Platos', 'resto_platos')
    nombres = consultas_negocio.nombres_seleccionados([_u('cual fue el plato mas vendido y cuanto gane este mes?')])
    assert {'platos_mas_vendidos', 'ganancia_del_local'} <= set(nombres)
    # Estas cruzan DetalleVenta.id_producto y en gastronomia (plato = servicio) darian vacio o ganancia sin costo.
    assert not set(nombres) & tools_ventas_local.TOOLS_BACKOFFICE_REEMPLAZADAS
    assert 'platos_mas_vendidos' not in consultas_negocio.nombres_seleccionados([_u('como esta la caja')])

    admin = SimpleNamespace(is_authenticated=True, es_admin=lambda: True, tiene_permiso=lambda c: True)
    sin_ventas = SimpleNamespace(is_authenticated=True, es_admin=lambda: False, tiene_permiso=lambda c: False)
    with app.app_context():
        r = consultas_negocio.ejecutar('platos_mas_vendidos', {'periodo': '7d'}, admin, 'plato mas vendido', cliente_id)
        assert r['ok'] and r['data']['platos'] == [] and r['data']['periodo'] == 'Ultimos 7 dias'
        r = consultas_negocio.ejecutar('ganancia_del_local', {'periodo': 'mes'}, admin, 'cuanto gane', cliente_id)
        assert r['ok'] and r['data']['totales']['ventas'] == 0 and 'dias' not in r['data']
        largo = {'periodo': 'custom', 'desde': '2026-01-01', 'hasta': '2026-11-01'}
        assert 'error' in consultas_negocio.ejecutar('ganancia_del_local', largo, admin, '', cliente_id)['data']
        assert consultas_negocio.ejecutar('platos_mas_vendidos', {}, sin_ventas, '', cliente_id)['error'] == 'sin_permiso_ventas'
