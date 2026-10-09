"""Historial de ventas como pantalla financiera.

Las ventas no tenian acceso en el menu lateral (solo desde tarjetas del
dashboard de servicios) y el historial abria con todas las ventas, sin totales
ni busqueda. Ahora hay un menu "Finanzas" con "Ventas" primero, el historial
abre en el dia de hoy con lo vendido / cobrado / a credito / anulado, y el
modal permite anular desde la lista.
"""
import re

from app import create_app, db
from app.models import Cliente, Configuracion, MetodoPago, SesionCaja, Usuario
from cobranzas import CLAVE_VENTAS_CREDITO_ACTIVO

from test_ventas_credito_modal_ui import (
    _crear_producto,
    _obtener_metodo_credito,
    _obtener_metodo_efectivo,
)


def _app_cliente():
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    return app, app.test_client()


def _loguear_admin(client):
    admin = Usuario.query.filter_by(username='admin').first()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin.id_usuario)
        sess['_fresh'] = True
    db.session.add(SesionCaja(id_caja=1, id_usuario=admin.id_usuario, monto_inicial=0, estado='abierta'))
    db.session.commit()
    return admin


def _vender(client, admin, cliente, producto, metodo, monto, request_id):
    resp = client.post('/ventas/procesar', json={
        'items': [{'id_producto': int(producto.id_producto), 'cantidad': 1}],
        'pagos': [{'id_metodo_pago': int(metodo.id_metodo_pago), 'monto': monto}],
        'id_cliente': int(cliente.id_cliente),
        'id_usuario_vendedor': int(admin.id_usuario),
        'client_request_id': request_id,
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return int(resp.get_json()['id_venta'])


def _cliente(nombre, ruc):
    cliente = Cliente(nombre=nombre, ruc_ci=ruc, tipo='minorista', limite_credito=900000, activo=True)
    db.session.add(cliente)
    db.session.commit()
    return cliente


def _bloque_menu(html, nombre):
    inicio = html.index(f'data-sidebar-menu="{nombre}"')
    return html[inicio:html.index('</template>', inicio)]


def test_menu_finanzas_agrupa_ventas_caja_y_contabilidad():
    app, client = _app_cliente()
    with app.app_context():
        _loguear_admin(client)
        html = client.get('/ventas/', follow_redirects=True).get_data(as_text=True)

        assert 'data-sidebar-trigger="finanzas"' in html
        finanzas = _bloque_menu(html, 'finanzas')
        for titulo in ('data-tab-title="Ventas"', 'data-tab-title="Caja"', 'data-tab-title="Contabilidad"'):
            assert titulo in finanzas

        operaciones = _bloque_menu(html, 'ventas')
        assert 'data-tab-title="POS"' in operaciones
        assert 'data-tab-title="Contabilidad"' not in operaciones
        assert 'data-tab-title="Caja"' not in operaciones


def test_historial_abre_en_hoy_con_totales_y_busca_por_cliente():
    app, client = _app_cliente()
    with app.app_context():
        admin = _loguear_admin(client)
        Configuracion.establecer_bool(CLAVE_VENTAS_CREDITO_ACTIVO, True)
        efectivo = _obtener_metodo_efectivo() or MetodoPago.query.first()
        credito = _obtener_metodo_credito()
        assert credito is not None

        ana = _cliente('Ana Historial', '7100100-1')
        beto = _cliente('Beto Historial', '7100200-1')
        _vender(client, admin, ana, _crear_producto(75000, 'HIST-FIN-001'), efectivo, 75000, 'hist-fin-1')
        _vender(client, admin, beto, _crear_producto(40000, 'HIST-FIN-002'), credito, 40000, 'hist-fin-2')

        html = client.get('/ventas/').get_data(as_text=True)
        assert 'Ana Historial' in html and 'Beto Historial' in html
        # Vendido 115.000; cobrado solo el contado; el resto a credito.
        assert '115.000' in html
        assert re.search(r'Cobrado</p>\s*<p[^>]*>₲&nbsp;75\.000', html)
        assert re.search(r'A crédito</p>\s*<p[^>]*>₲&nbsp;40\.000', html)

        filtrado = client.get('/ventas/?rango=hoy&q=ana').get_data(as_text=True)
        assert 'Ana Historial' in filtrado
        assert 'Beto Historial' not in filtrado

        anuladas = client.get('/ventas/?rango=hoy&estado=anulada').get_data(as_text=True)
        assert 'No hay ventas para este filtro.' in anuladas


def test_historial_busca_por_numero_de_venta():
    app, client = _app_cliente()
    with app.app_context():
        admin = _loguear_admin(client)
        efectivo = _obtener_metodo_efectivo() or MetodoPago.query.first()
        cliente = _cliente('Carla Numero', '7100300-1')
        venta_id = _vender(client, admin, cliente, _crear_producto(10000, 'HIST-FIN-003'), efectivo, 10000, 'hist-fin-3')

        html = client.get(f'/ventas/?todas=1&q=%23{venta_id}').get_data(as_text=True)
        assert 'Carla Numero' in html


def test_modal_informa_si_la_venta_se_puede_anular():
    app, client = _app_cliente()
    with app.app_context():
        admin = _loguear_admin(client)
        efectivo = _obtener_metodo_efectivo() or MetodoPago.query.first()
        cliente = _cliente('Dario Modal', '7100400-1')
        venta_id = _vender(client, admin, cliente, _crear_producto(20000, 'HIST-FIN-004'), efectivo, 20000, 'hist-fin-4')

        detalle = client.get(f'/reportes/ventas/{venta_id}/detalle').get_json()
        assert detalle['estado'] == 'completada'
        assert detalle['puede_anular'] is True


def test_dashboard_gastronomia_ofrece_la_tarjeta_ventas():
    from gastronomia.services.dashboard_preferences import build_dashboard_cards

    class _Usuario:
        def get_preferencia(self, *_args, **_kwargs):
            return ''

    cards = build_dashboard_cards(_Usuario(), {'ventas': True}, contexto_operativo=True)
    assert [c['endpoint'] for c in cards] == ['ventas.listar']
    assert build_dashboard_cards(_Usuario(), {'ventas': False}, contexto_operativo=True) == []


def test_con_facturacion_electronica_muestra_columna_y_acciones_nc():
    from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

    app, client = _app_cliente()
    with app.app_context():
        admin = _loguear_admin(client)
        Configuracion.establecer(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, 'true')
        db.session.commit()
        efectivo = _obtener_metodo_efectivo() or MetodoPago.query.first()
        cliente = _cliente('Elena Factura', '7100500-1')
        venta_id = _vender(client, admin, cliente, _crear_producto(30000, 'HIST-FIN-005'), efectivo, 30000, 'hist-fin-5')

        html = client.get('/ventas/').get_data(as_text=True)
        assert '>Factura</th>' in html
        assert 'Anular con NC' in html
        assert 'venta.fe.url_anular_nc' in html

        detalle = client.get(f'/reportes/ventas/{venta_id}/detalle').get_json()
        assert detalle['fe'] is not None
        assert detalle['fe']['url_anular_nc'].endswith(f'/anular-con-nota-credito/{venta_id}')


def test_buscar_sin_fechas_recorre_todo_el_historial():
    """El formulario manda desde/hasta vacios: buscar no debe volver a "hoy"."""
    from app.services.ventas_listado import leer_filtros

    filtros = leer_filtros({'q': 'aida', 'desde': '', 'hasta': '', 'estado': ''})
    assert filtros['desde'] is None and filtros['hasta'] is None
    assert filtros['todas'] is True

    sin_nada = leer_filtros({})
    assert sin_nada['rango'] == 'hoy' and sin_nada['desde'] is not None


def test_cobrado_descuenta_el_vuelto():
    """El pago guarda lo que entrego el cliente; el vuelto no es cobro."""
    app, client = _app_cliente()
    with app.app_context():
        admin = _loguear_admin(client)
        efectivo = _obtener_metodo_efectivo() or MetodoPago.query.first()
        cliente = _cliente('Fabio Vuelto', '7100600-1')
        _vender(client, admin, cliente, _crear_producto(8000, 'HIST-FIN-006'), efectivo, 20000, 'hist-fin-6')

        html = client.get('/ventas/').get_data(as_text=True)
        assert re.search(r'Cobrado</p>\s*<p[^>]*>₲&nbsp;8\.000', html)
