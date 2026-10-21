"""Fase 1 (paso 10) del plan de pasteleria: root enciende encargos y fija sus parametros."""
import re

from app import create_app, db
from gastronomia.models import GastronomiaClienteConfig
from gastronomia.services.pasteleria_flags import parametros_encargos
from test_gastronomia_caja import _loguear
from test_gastronomia_pedidos import _crear_menu_para_pedidos


def _csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _root(app):
    client = app.test_client()
    _loguear(client, app, 'root')
    html = client.get('/usuarios/modulos-sistema').get_data(as_text=True)
    return client, _csrf(html), html


def _config(app, cliente_id):
    with app.app_context():
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).one()
        return {
            'activo': config.encargos_activo,
            'anticipo': config.encargos_anticipo_horas,
            'tope': config.encargos_max_por_dia,
            'fotos': config.encargos_max_fotos,
            'opciones': config.encargos_cancelacion_opciones,
        }


def test_root_ve_el_panel_y_enciende_encargos_con_parametros():
    app = create_app('testing')
    cliente_id, _, _ = _crear_menu_para_pedidos(app, 'Config Enc 1', 'config_enc_1')
    client, csrf, html = _root(app)
    assert 'Encargos (pasteleria / cafeteria)' in html
    assert f'data-pasteleria-cliente="{cliente_id}"' in html

    resp = client.post(f'/usuarios/modulos-sistema/pasteleria/{cliente_id}', data={
        'csrf_token': csrf,
        'encargos_activo': '1',
        'encargos_anticipo_horas': '24',
        'encargos_max_por_dia': '8',
        'encargos_max_fotos': '3',
        'encargos_cancelacion_opciones': ['devolver_todo', 'retener_parcial'],
    })
    assert resp.status_code in (302, 303)
    assert _config(app, cliente_id) == {
        'activo': True, 'anticipo': 24, 'tope': 8, 'fotos': 3, 'opciones': 'devolver_todo,retener_parcial',
    }
    with app.app_context():
        assert parametros_encargos(cliente_id)['opciones_cancelacion'] == ['devolver_todo', 'retener_parcial']

    # El local ya ve la tarjeta de encargos.
    local = app.test_client()
    _loguear(local, app, 'config_enc_1')
    assert 'data-dashboard-card-id="encargos"' in local.get('/gastronomia/').get_data(as_text=True)


def test_campos_vacios_vuelven_a_los_valores_base_y_apagar_funciona():
    app = create_app('testing')
    cliente_id, _, _ = _crear_menu_para_pedidos(app, 'Config Enc 2', 'config_enc_2')
    client, csrf, _ = _root(app)
    client.post(f'/usuarios/modulos-sistema/pasteleria/{cliente_id}', data={
        'csrf_token': csrf, 'encargos_activo': '1', 'encargos_max_por_dia': '4',
        'encargos_cancelacion_opciones': ['retener_todo'],
    })

    client.post(f'/usuarios/modulos-sistema/pasteleria/{cliente_id}', data={
        'csrf_token': csrf, 'encargos_anticipo_horas': '', 'encargos_max_por_dia': '', 'encargos_max_fotos': '',
        'encargos_cancelacion_opciones': ['devolver_todo', 'retener_todo', 'retener_parcial'],
    })
    assert _config(app, cliente_id) == {
        'activo': False, 'anticipo': 0, 'tope': None, 'fotos': 5,
        'opciones': 'devolver_todo,retener_todo,retener_parcial',
    }


def test_datos_invalidos_no_cambian_nada():
    app = create_app('testing')
    cliente_id, _, _ = _crear_menu_para_pedidos(app, 'Config Enc 3', 'config_enc_3')
    client, csrf, _ = _root(app)
    antes = _config(app, cliente_id)

    for data in (
        {'encargos_activo': '1'},  # sin opciones de cancelacion
        {'encargos_activo': '1', 'encargos_anticipo_horas': '9999', 'encargos_cancelacion_opciones': ['devolver_todo']},
        {'encargos_activo': '1', 'encargos_max_fotos': 'muchas', 'encargos_cancelacion_opciones': ['devolver_todo']},
    ):
        resp = client.post(
            f'/usuarios/modulos-sistema/pasteleria/{cliente_id}',
            data={'csrf_token': csrf, **data},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            db.session.rollback()
        assert _config(app, cliente_id) == antes


def test_solo_root_puede_configurar_encargos():
    app = create_app('testing')
    cliente_id, _, _ = _crear_menu_para_pedidos(app, 'Config Enc 4', 'config_enc_4')
    client = app.test_client()
    _loguear(client, app, 'config_enc_4')  # administrador del negocio, no root
    html = client.get('/gastronomia/pos').get_data(as_text=True)
    csrf = re.search(r'id="csrf-token" value="([^"]+)"', html).group(1)

    assert client.get('/usuarios/modulos-sistema').status_code == 403
    resp = client.post(
        f'/usuarios/modulos-sistema/pasteleria/{cliente_id}',
        data={'csrf_token': csrf, 'encargos_activo': '1', 'encargos_cancelacion_opciones': ['devolver_todo']},
    )
    assert resp.status_code == 403
    assert _config(app, cliente_id)['activo'] is False
