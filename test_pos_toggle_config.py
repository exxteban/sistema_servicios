import re

from app import create_app, db
from app.models import Configuracion, Usuario
from control_de_empleados import CLAVE_MODULO_CONTROL_EMPLEADOS


CLAVE = 'pos_ocultar_selector_vendedor_cajero'
CLAVE_CAJA_FLUJO = 'caja_flujo_enviado_desde_vendedor'
CLAVE_CAJA_ALERTA = 'caja_alerta_pendientes_activa'
CLAVE_CAJA_EXIGIR = 'caja_exigir_cajero_para_cobro'


def _extraer_csrf(html):
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html or '')
    assert m is not None
    return m.group(1)


def _loguear_admin(client, app):
    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        admin_id = admin.id_usuario
    with client.session_transaction() as s:
        s['_user_id'] = str(admin_id)
        s['_fresh'] = True


def _loguear_root(client, app):
    with app.app_context():
        root = Usuario.query.filter_by(username='root').first()
        assert root is not None
        root_id = root.id_usuario
    with client.session_transaction() as s:
        s['_user_id'] = str(root_id)
        s['_fresh'] = True


def test_config_pos_default_desactivado_si_no_existe():
    app = create_app('testing')
    with app.app_context():
        cfg = db.session.get(Configuracion, CLAVE)
        if cfg:
            db.session.delete(cfg)
            db.session.commit()

        # Desactivado por defecto: no mostrar selector en POS.
        assert Configuracion.obtener_bool(CLAVE, default=False) is False


def test_parse_bool_configuracion_es_robusto():
    assert Configuracion.parse_bool(True, default=False) is True
    assert Configuracion.parse_bool(False, default=True) is False
    assert Configuracion.parse_bool(1, default=False) is True
    assert Configuracion.parse_bool(0, default=True) is False
    assert Configuracion.parse_bool('1', default=False) is True
    assert Configuracion.parse_bool('0', default=True) is False
    assert Configuracion.parse_bool('on', default=False) is True
    assert Configuracion.parse_bool('off', default=True) is False
    assert Configuracion.parse_bool('SI', default=False) is True
    assert Configuracion.parse_bool('NO', default=True) is False
    assert Configuracion.parse_bool('valor_desconocido', default=False) is False
    assert Configuracion.parse_bool('valor_desconocido', default=True) is True


def test_toggle_configuracion_pos_persiste_activado_y_desactivado():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    resp_get = client.get('/usuarios/configuracion')
    assert resp_get.status_code == 200
    csrf = _extraer_csrf(resp_get.get_data(as_text=True))

    resp_on = client.post(
        '/usuarios/configuracion',
        data={
            'csrf_token': csrf,
            'mostrar_selector_vendedor_pos': '1',
        },
        follow_redirects=False,
    )
    assert resp_on.status_code in (302, 303)
    with app.app_context():
        cfg = db.session.get(Configuracion, CLAVE)
        assert cfg is not None
        assert cfg.valor == '1'
        assert Configuracion.obtener_bool(CLAVE, default=False) is True

    resp_get = client.get('/usuarios/configuracion')
    assert resp_get.status_code == 200
    csrf = _extraer_csrf(resp_get.get_data(as_text=True))

    resp_off = client.post(
        '/usuarios/configuracion',
        data={
            'csrf_token': csrf,
            'mostrar_selector_vendedor_pos': '0',
        },
        follow_redirects=False,
    )
    assert resp_off.status_code in (302, 303)
    with app.app_context():
        cfg = db.session.get(Configuracion, CLAVE)
        assert cfg is not None
        assert cfg.valor == '0'
        assert Configuracion.obtener_bool(CLAVE, default=False) is False


def test_toggle_configuracion_caja_persiste_flags():
    app = create_app('testing')
    client = app.test_client()
    _loguear_admin(client, app)

    resp_get = client.get('/usuarios/configuracion')
    assert resp_get.status_code == 200
    csrf = _extraer_csrf(resp_get.get_data(as_text=True))

    resp_on = client.post(
        '/usuarios/configuracion',
        data={
            'csrf_token': csrf,
            'mostrar_selector_vendedor_pos': '1',
            'modo_cobro_exclusivo_cajero': '1',
            'caja_alerta_pendientes_activa': '1',
        },
        follow_redirects=False,
    )
    assert resp_on.status_code in (302, 303)
    with app.app_context():
        assert Configuracion.obtener_bool(CLAVE_CAJA_FLUJO, default=False) is True
        assert Configuracion.obtener_bool(CLAVE_CAJA_ALERTA, default=False) is True
        assert Configuracion.obtener_bool(CLAVE_CAJA_EXIGIR, default=False) is True

    resp_get = client.get('/usuarios/configuracion')
    assert resp_get.status_code == 200
    csrf = _extraer_csrf(resp_get.get_data(as_text=True))

    resp_off = client.post(
        '/usuarios/configuracion',
        data={
            'csrf_token': csrf,
            'mostrar_selector_vendedor_pos': '0',
            'modo_cobro_exclusivo_cajero': '0',
            'caja_alerta_pendientes_activa': '0',
        },
        follow_redirects=False,
    )
    assert resp_off.status_code in (302, 303)
    with app.app_context():
        assert Configuracion.obtener_bool(CLAVE_CAJA_FLUJO, default=True) is False
        assert Configuracion.obtener_bool(CLAVE_CAJA_ALERTA, default=True) is False
        assert Configuracion.obtener_bool(CLAVE_CAJA_EXIGIR, default=True) is False


def test_toggle_modulo_control_empleados_se_refleja_en_ui_y_menu():
    app = create_app('testing')
    client = app.test_client()
    _loguear_root(client, app)

    resp_get = client.get('/usuarios/modulos-sistema')
    assert resp_get.status_code == 200
    csrf = _extraer_csrf(resp_get.get_data(as_text=True))

    resp_on = client.post(
        '/usuarios/modulos-sistema',
        data={
            'csrf_token': csrf,
            CLAVE_MODULO_CONTROL_EMPLEADOS: '1',
            'flujo_caja_activo': '1',
        },
        follow_redirects=False,
    )
    assert resp_on.status_code in (302, 303)
    with app.app_context():
        assert Configuracion.obtener_bool(CLAVE_MODULO_CONTROL_EMPLEADOS, default=False) is True

    resp_get = client.get('/usuarios/modulos-sistema')
    assert resp_get.status_code == 200
    html = resp_get.get_data(as_text=True)

    assert re.search(r'id="control_empleados_activo"[\s\S]*?checked', html) is not None
    assert '/control-empleados/' in html
