"""Teclas rapidas (F2, F4...) por rubro y "vs ayer" de los inicios de servicios y gastronomia."""
import json
import re
from datetime import datetime, timedelta

from app import create_app, db
from app.models import Cliente, Configuracion, Usuario
from app.services.atajos_teclado import TECLAS, contexto_atajos, limpiar, set_atajos
from app.services.comparacion_ayer import tendencia, texto_diferencia_monto, ventana_ayer_misma_hora
from gastronomia.services.modo_operacion import MODO_GASTRONOMIA


def _crear_usuario(app, username='atajos_admin'):
    with app.app_context():
        cliente = Cliente(nombre='Negocio Test', ruc_ci='9100', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(
            id_cliente=cliente.id_cliente,
            username=username,
            nombre_completo='Admin Atajos',
            id_rol=1,
            activo=True,
        )
        usuario.set_password('clave123')
        db.session.add(usuario)
        db.session.commit()
        return usuario.id_usuario


def _loguear(client, user_id):
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def _csrf(html):
    match = re.search(r'name="csrf-token" content="([^"]+)"', html) or re.search(
        r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _activar_gastronomia(app):
    with app.app_context():
        Configuracion.establecer('modo_operacion_principal', MODO_GASTRONOMIA)


# ---- limpieza de teclas ----

def test_limpiar_descarta_teclas_raras_acciones_ajenas_y_repetidas():
    data = {'f2': 'pos', 'F3': 'caja', 'F4': 'pos', 'F8': 'inventada', 'F10': 'caja'}
    assert limpiar(data, {'pos', 'caja'}) == {'F2': 'pos', 'F10': 'caja'}


def test_limpiar_respeta_el_orden_de_las_teclas_y_no_el_del_json():
    # F10 va antes que F2 alfabeticamente: igual gana F2.
    assert limpiar({'F10': 'pos', 'F2': 'pos'}, {'pos'}) == {'F2': 'pos'}
    assert limpiar('no es dict', {'pos'}) == {}
    assert 'F5' not in TECLAS and 'F1' not in TECLAS


# ---- gastronomia ----

def test_gastronomia_trae_pos_en_f2_y_abrir_caja_en_f4_por_defecto():
    app = create_app('testing')
    user_id = _crear_usuario(app)
    _activar_gastronomia(app)
    with app.test_request_context('/'):
        from flask_login import login_user
        usuario = db.session.get(Usuario, user_id)
        login_user(usuario)
        ctx = contexto_atajos(usuario)
        assert ctx['perfil'] == 'gastronomia'
        assert ctx['atajos'] == {'F2': 'pos', 'F4': 'abrir_caja'}
        ids = {accion['id'] for accion in ctx['disponibles']}
        assert {'pos', 'salon', 'cocina', 'caja', 'abrir_caja', 'menu', 'salon_config'} <= ids
        urls = {accion['tecla']: accion['url'] for accion in ctx['acciones']}
        assert urls['F2'].endswith('/gastronomia/pos')
        assert urls['F4'].endswith('/caja/abrir')


def test_gastronomia_guarda_teclas_y_dashboard_muestra_boton_y_chips():
    app = create_app('testing')
    client = app.test_client()
    user_id = _crear_usuario(app)
    _activar_gastronomia(app)
    _loguear(client, user_id)

    html = client.get('/gastronomia/').get_data(as_text=True)
    assert 'data-atajos-configurar' in html
    assert 'data-atajo-accion="pos"' in html
    assert 'data-atajo-accion="menu"' in html
    assert 'window.__atajosTeclado' in html

    res = client.post(
        '/api/atajos-teclado',
        data=json.dumps({'atajos': {'F2': 'salon', 'F8': 'menu', 'F9': 'salon', 'F3': 'cocina'}}),
        content_type='application/json',
        headers={'X-CSRFToken': _csrf(html)},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data['atajos']['atajos'] == {'F2': 'salon', 'F8': 'menu'}

    # Vacio tambien se guarda: no vuelven las de fabrica.
    res = client.post(
        '/api/atajos-teclado', data=json.dumps({'atajos': {}}),
        content_type='application/json', headers={'X-CSRFToken': _csrf(html)},
    )
    assert res.get_json()['atajos']['atajos'] == {}
    assert res.get_json()['atajos']['defaults'] == {'F2': 'pos', 'F4': 'abrir_caja'}


def test_api_rechaza_teclas_que_no_son_un_objeto():
    app = create_app('testing')
    client = app.test_client()
    user_id = _crear_usuario(app)
    _loguear(client, user_id)
    html = client.get('/').get_data(as_text=True)
    res = client.post(
        '/api/atajos-teclado', data=json.dumps({'atajos': ['F2']}),
        content_type='application/json', headers={'X-CSRFToken': _csrf(html)},
    )
    assert res.status_code == 400


def test_gastronomia_resumen_trae_comparacion_vs_ayer():
    from gastronomia.models import GastronomiaPedidoPago
    from gastronomia.services.dashboard_resumen_service import _cobrado_entre

    app = create_app('testing')
    _crear_usuario(app)
    with app.app_context():
        inicio, fin = ventana_ayer_misma_hora()
        assert inicio <= fin
        cliente_id = Cliente.query.filter_by(ruc_ci='9100').first().id_cliente
        total, cantidad = _cobrado_entre(cliente_id, inicio, fin)
        assert (total, cantidad) == (0.0, 0)
        assert GastronomiaPedidoPago is not None


# ---- servicios ----

def test_servicios_trae_cobrar_en_f2_y_acciones_del_rubro():
    app = create_app('testing')
    user_id = _crear_usuario(app)
    with app.test_request_context('/'):
        from flask_login import login_user
        usuario = db.session.get(Usuario, user_id)
        login_user(usuario)
        ctx = contexto_atajos(usuario)
        assert ctx['perfil'] == 'servicios'
        assert ctx['atajos']['F2'] == 'ventas'
        ids = {accion['id'] for accion in ctx['disponibles']}
        assert {'ventas', 'abrir_caja', 'cliente_nuevo'} <= ids
        guardado = set_atajos(usuario, {'F9': 'cliente_nuevo', 'F2': 'no_existe'})
        assert guardado == {'F9': 'cliente_nuevo'}


def test_servicios_dashboard_muestra_boton_teclas():
    app = create_app('testing')
    client = app.test_client()
    user_id = _crear_usuario(app)
    with app.app_context():
        Configuracion.establecer('dashboard_negocio_activo', 'servicios')
    _loguear(client, user_id)
    html = client.get('/').get_data(as_text=True)
    assert 'data-atajos-configurar' in html
    assert 'data-atajo-accion="ventas"' in html


# ---- textos vs ayer ----

def test_textos_vs_ayer():
    app = create_app('testing')
    with app.app_context():
        assert texto_diferencia_monto(100, 100) == 'Igual que ayer'
        assert texto_diferencia_monto(150000, 100000).endswith('más que ayer')
        assert '50.000' in texto_diferencia_monto(150000, 100000)
        assert texto_diferencia_monto(0, 20000).endswith('menos que ayer')
    assert tendencia(2, 1) == 'mas'
    assert tendencia(1, 2) == 'menos'
    assert tendencia(1, 1) == 'igual'


def test_ventana_ayer_corta_a_la_misma_hora():
    app = create_app('testing')
    with app.app_context():
        ahora = datetime.utcnow()
        inicio, fin = ventana_ayer_misma_hora(ahora)
        assert fin <= ahora - timedelta(days=1) + timedelta(seconds=1)
        assert inicio < fin or inicio == fin
