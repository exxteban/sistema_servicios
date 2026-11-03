"""Un usuario sin permiso de menu no cambia nada del BI por sus acciones (cola, comision, activacion)."""
from app import create_app
from gastronomia.services.bi.activacion import lista_activacion
from gastronomia.services.bi.cola_config import SEGMENTOS_PLANTILLA, leer_config
from gastronomia.services.bi.comision import leer_porcentajes
from test_gastronomia_bi_reporte import _crear_negocio, _csrf, _loguear

CONFIG_COLA = {
    'limite_dia': '99', 'frecuencia_dias': '14', 'segunda_min': '5', 'segunda_max': '15',
    **{f'pl_{segmento}': 'Hola {nombre}' for segmento in SEGMENTOS_PLANTILLA},
}

TITULOS_BI = ('Tu mes en el sistema', 'Clientes que vuelven', 'Activación comercial')

RUTAS_CON_PERMISO_MENU = (
    ('/gastronomia/bi/cola/abrir', {'contacto_id': '1'}),
    ('/gastronomia/bi/cola/enviado', {'contacto_id': '1'}),
    ('/gastronomia/bi/cola/omitir', {'contacto_id': '1'}),
    ('/gastronomia/bi/cola/no-quiere', {'contacto_id': '1'}),
    ('/gastronomia/bi/cola/configuracion', CONFIG_COLA),
    ('/gastronomia/bi/comision', {'comision_pedidosya': '30'}),
    ('/gastronomia/bi/activacion/qr_impreso', {'hecho': '1'}),
)


def _post(client, ruta, datos, csrf):
    return client.post(ruta, data={**datos, 'csrf_token': csrf}, headers={'X-CSRFToken': csrf})


def _estado(app, cliente_id):
    with app.app_context():
        return {
            'comision': leer_porcentajes(cliente_id)['pedidosya'],
            'limite_dia': leer_config(cliente_id)['limite_dia'],
            'activacion': lista_activacion(cliente_id)['completados'],
        }


def test_sin_permiso_de_menu_las_acciones_no_cambian_nada(monkeypatch):
    app = create_app('testing')
    cliente_id = _crear_negocio(app, 'bi_permisos')[0]
    client = app.test_client()
    _loguear(client, app, 'bi_permisos')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))
    inicial = _estado(app, cliente_id)

    with monkeypatch.context() as sin_permiso:
        sin_permiso.setattr('gastronomia.services.permisos.tiene_permiso_gastronomia', lambda *codigos: False)
        for ruta, datos in RUTAS_CON_PERMISO_MENU:
            respuesta = _post(client, ruta, datos, csrf)
            assert respuesta.status_code in (302, 403), ruta
            assert '/inteligencia' not in (respuesta.headers.get('Location') or ''), ruta
    assert _estado(app, cliente_id) == inicial

    # Control: con permiso, las mismas rutas si cambian el estado (la prueba detecta la diferencia).
    destinos = {}
    for ruta, datos in RUTAS_CON_PERMISO_MENU[4:]:
        respuesta = _post(client, ruta, datos, csrf)
        assert respuesta.status_code == 302
        destinos[ruta] = respuesta.headers['Location']
    # Cada accion vuelve a su sub-pestana de Gastronomia.
    assert destinos['/gastronomia/bi/cola/configuracion'].endswith('#gastro-clientes')
    assert destinos['/gastronomia/bi/comision'].endswith('#gastro-resultados')
    assert destinos['/gastronomia/bi/activacion/qr_impreso'].endswith('#gastro-crecer')
    final = _estado(app, cliente_id)
    assert final['comision'] == 30.0
    assert final['limite_dia'] == 99
    assert final['activacion'] == inicial['activacion'] + 1


def test_interruptor_oculta_los_bloques_sin_borrar_datos_y_solo_lo_cambia_root():
    from app.models import Configuracion
    from gastronomia.services.bi.interruptor import bi_activo
    from test_gastronomia_bi_salud import _ajustar_root, _restaurar_root

    app = create_app('testing')
    cliente_id, usuario_id, _ = _crear_negocio(app, 'bi_interruptor')
    client = app.test_client()
    _loguear(client, app, 'bi_interruptor')
    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))

    with app.app_context():
        assert bi_activo(cliente_id) is True
    html = client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)
    for titulo in TITULOS_BI:
        assert titulo in html

    assert _post(client, '/gastronomia/bi/activo', {'activo': '0'}, csrf).status_code == 403

    anterior = _ajustar_root(app, usuario_id)
    try:
        assert _post(client, '/gastronomia/bi/activo', {'activo': '0'}, csrf).status_code == 302
        with app.app_context():
            assert bi_activo(cliente_id) is False
            assert Configuracion.obtener(f'gastronomia_bi_activo_{cliente_id}') == '0'
        apagado = client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)
        for titulo in TITULOS_BI:
            assert titulo not in apagado
        assert 'Desactivada' in client.get('/gastronomia/bi/salud-uso').get_data(as_text=True)

        assert _post(client, '/gastronomia/bi/activo', {'activo': '1'}, csrf).status_code == 302
        with app.app_context():
            assert bi_activo(cliente_id) is True
    finally:
        _restaurar_root(app, anterior)
