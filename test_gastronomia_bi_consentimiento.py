"""BI-04: casilla de consentimiento para recibir mensajes desde el POS, filtro de la cola y API (datos ficticios)."""
import pytest

from app import create_app
from gastronomia.bi_models import GastronomiaBiConsentimiento
from gastronomia.services.bi.consentimiento import (
    contar_sin_marcar,
    registrar_casilla,
    telefonos_con_consentimiento,
)
from gastronomia.services.bi.cola import construir_cola, hoy_local, resumen_cola
from test_gastronomia_bi_cola import _crear_negocio, _csrf, _habitual, _loguear, _pedido


def test_casilla_marcada_normaliza_el_telefono_y_no_duplica():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI04 Normaliza', 'bi04_normaliza')
    with app.app_context():
        assert registrar_casilla(cliente_id, '0981 400 001', True) == 'registrado'
        assert registrar_casilla(cliente_id, '+595981400001', True) == 'ya_registrado'
        assert telefonos_con_consentimiento(cliente_id) == {'+595981400001'}
        assert GastronomiaBiConsentimiento.query.filter_by(cliente_id=cliente_id).count() == 1


def test_casilla_rechaza_telefonos_invalidos_sin_guardar_nada():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI04 Invalidos', 'bi04_invalidos')
    with app.app_context():
        for celular in ('', None, 'abc', '12'):
            for acepta in (True, False):
                with pytest.raises(ValueError):
                    registrar_casilla(cliente_id, celular, acepta)
        assert telefonos_con_consentimiento(cliente_id) == set()
        assert contar_sin_marcar(cliente_id) == 0


def test_casilla_sin_marcar_queda_pendiente_y_no_entra_en_la_cola():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI04 Pendiente', 'bi04_pendiente')
    _pedido(app, cliente_id, usuario_id, producto_id, 10, celular='0981 460 001', nombre='Sin marcar')
    with app.app_context():
        assert registrar_casilla(cliente_id, '0981 460 001', False) == 'sin_marcar'
        assert contar_sin_marcar(cliente_id) == 1
        assert telefonos_con_consentimiento(cliente_id) == set()
        _, disponibles = construir_cola(cliente_id, hoy_local())
        assert disponibles == []
        resumen = resumen_cola(cliente_id)
    assert resumen['hay_consentimientos'] is False


def test_casilla_marcada_despues_saca_el_pendiente_y_habilita_la_cola():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI04 Acepta despues', 'bi04_acepta_despues')
    _habitual(app, cliente_id, usuario_id, producto_id, '0981 470 099', 'Previo')
    with app.app_context():
        registrar_casilla(cliente_id, '0981 470 001', False)
        assert contar_sin_marcar(cliente_id) == 1
        assert registrar_casilla(cliente_id, '0981 470 001', True) == 'registrado'
        assert contar_sin_marcar(cliente_id) == 0
        assert '+595981470001' in telefonos_con_consentimiento(cliente_id)


def test_desmarcar_no_revoca_un_consentimiento_ya_registrado():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI04 No revoca', 'bi04_no_revoca')
    with app.app_context():
        registrar_casilla(cliente_id, '0981 480 001', True)
        assert registrar_casilla(cliente_id, '0981 480 001', False) == 'ya_registrado'
        assert telefonos_con_consentimiento(cliente_id) == {'+595981480001'}
        assert contar_sin_marcar(cliente_id) == 0


def test_cola_solo_contacta_telefonos_con_consentimiento():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI04 Cola', 'bi04_cola')
    # _habitual registra la casilla marcada del telefono que usa.
    _habitual(app, cliente_id, usuario_id, producto_id, '0981 410 001', 'Acepto')
    for dias in (30, 23, 16, 9):
        _pedido(app, cliente_id, usuario_id, producto_id, dias, celular='0981 410 002', nombre='No acepto')
    with app.app_context():
        _, disponibles = construir_cola(cliente_id, hoy_local())
    assert [candidato['telefono'] for candidato in disponibles] == ['+595981410001']


def test_resumen_indica_cuando_nadie_consintio():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI04 Sin Consentimiento', 'bi04_sin_consentimiento')
    _pedido(app, cliente_id, usuario_id, producto_id, 10, celular='0981 420 001', nombre='Nadie')
    with app.app_context():
        resumen = resumen_cola(cliente_id)
    assert resumen['hay_telefonos'] is True
    assert resumen['hay_consentimientos'] is False
    assert resumen['en_cola'] == 0


def test_api_informa_el_resultado_de_la_casilla_y_rechaza_telefono_invalido():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, _, _ = _crear_negocio(app, 'BI04 API', 'bi04_api')
    _loguear(client, app, 'bi04_api')
    csrf = _csrf(client.get('/gastronomia/pos').get_data(as_text=True))
    cabeceras = {'X-CSRFToken': csrf}

    marcada = client.post('/api/gastronomia/bi/consentimiento', json={'celular': '0981 430 001', 'acepta': True}, headers=cabeceras)
    sin_marcar = client.post('/api/gastronomia/bi/consentimiento', json={'celular': '0981 430 002', 'acepta': False}, headers=cabeceras)
    ya_registrado = client.post('/api/gastronomia/bi/consentimiento', json={'celular': '0981 430 001', 'acepta': False}, headers=cabeceras)
    invalida = client.post('/api/gastronomia/bi/consentimiento', json={'celular': 'abc', 'acepta': True}, headers=cabeceras)

    assert marcada.status_code == 200
    assert marcada.get_json() == {'ok': True, 'estado': 'registrado'}
    assert sin_marcar.get_json() == {'ok': True, 'estado': 'sin_marcar'}
    assert ya_registrado.get_json() == {'ok': True, 'estado': 'ya_registrado'}
    assert invalida.status_code == 400
    assert invalida.get_json()['error'] == 'validation_error'
    with app.app_context():
        assert telefonos_con_consentimiento(cliente_id) == {'+595981430001'}
        assert contar_sin_marcar(cliente_id) == 1


def test_api_no_registra_sin_sesion():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI04 Anonimo', 'bi04_anonimo')
    anonimo = app.test_client()

    respuesta = anonimo.post('/api/gastronomia/bi/consentimiento', json={'celular': '0981 440 001', 'acepta': True})

    assert respuesta.status_code != 200
    with app.app_context():
        assert telefonos_con_consentimiento(cliente_id) == set()


def test_tab_avisa_que_nadie_consintio_y_el_pos_muestra_la_casilla():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'BI04 Tab', 'bi04_tab')
    _pedido(app, cliente_id, usuario_id, producto_id, 10, celular='0981 450 001', nombre='Sin casilla')
    _loguear(client, app, 'bi04_tab')

    html = client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)
    assert 'Todavía no hay clientes que hayan aceptado recibir mensajes' in html

    pos = client.get('/gastronomia/pos').get_data(as_text=True)
    assert 'id="cliente-acepta-mensajes"' in pos
    assert pos.count('id="delivery-phone"') == 1
    assert 'js/pos_consentimiento.js' in pos


def test_tablero_cuenta_los_celulares_guardados_sin_casilla_marcada():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, _, _ = _crear_negocio(app, 'BI04 Pendientes', 'bi04_pendientes')
    with app.app_context():
        registrar_casilla(cliente_id, '0981 490 001', False)
        registrar_casilla(cliente_id, '0981 490 002', False)
    _loguear(client, app, 'bi04_pendientes')

    html = client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)

    assert 'Celulares cargados sin la casilla de consentimiento marcada: 2' in html
