"""BI-05: aceptacion de mensajes en el checkout de la tienda online, por la API publica (datos ficticios)."""
from app import create_app, db
from app.models import Configuracion, Usuario
from gastronomia.bi_models import GastronomiaBiConsentimiento
from gastronomia.services.bi.consentimiento import contar_sin_marcar, registrar_casilla, telefonos_con_consentimiento
from gastronomia.services.modo_operacion import CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA, MODO_SERVICIOS
from test_tienda_gastronomia_presupuesto import _crear_tienda_gastronomia


def _preparar_tienda(slug: str):
    Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_GASTRONOMIA)
    tienda, producto = _crear_tienda_gastronomia(slug=slug)
    admin = Usuario.query.filter_by(username='admin').first()
    admin.id_cliente = tienda.id_cliente
    db.session.commit()
    return tienda.id_cliente, tienda.slug, producto.id_producto


def _pedido_tienda(client, slug: str, producto_id: int, celular: str, **extra):
    return client.post(f'/api/tienda/{slug}/gastronomia/pedido', json={
        'tipo_pedido': 'retiro',
        'nombre': 'Cliente BI05',
        'celular': celular,
        'items': [{'id': producto_id, 'quantity': 1}],
        **extra,
    })


def _restaurar_modo(app):
    with app.app_context():
        Configuracion.establecer(CLAVE_MODO_OPERACION_PRINCIPAL, MODO_SERVICIOS)


def test_checkout_con_aceptacion_registra_el_consentimiento():
    app = create_app('testing')
    client = app.test_client()
    with app.app_context():
        cliente_id, slug, producto_id = _preparar_tienda('bi05-consent-si')
    try:
        respuesta = _pedido_tienda(client, slug, producto_id, '0981 600 001', acepta_mensajes=True)
        assert respuesta.status_code == 201
        with app.app_context():
            assert telefonos_con_consentimiento(cliente_id) == {'+595981600001'}
            assert contar_sin_marcar(cliente_id) == 0
    finally:
        _restaurar_modo(app)


def test_checkout_sin_aceptacion_no_deja_nada_registrado():
    app = create_app('testing')
    client = app.test_client()
    with app.app_context():
        cliente_id, slug, producto_id = _preparar_tienda('bi05-consent-no')
    try:
        assert _pedido_tienda(client, slug, producto_id, '0981 610 001').status_code == 201
        assert _pedido_tienda(client, slug, producto_id, '0981 610 002', acepta_mensajes=False).status_code == 201
        # Solo un «true» exacto cuenta: cualquier otro valor no es una aceptacion.
        assert _pedido_tienda(client, slug, producto_id, '0981 610 003', acepta_mensajes='true').status_code == 201
        with app.app_context():
            assert GastronomiaBiConsentimiento.query.filter_by(cliente_id=cliente_id).count() == 0
            assert contar_sin_marcar(cliente_id) == 0
    finally:
        _restaurar_modo(app)


def test_checkout_con_aceptacion_resuelve_un_pendiente_del_pos():
    app = create_app('testing')
    client = app.test_client()
    with app.app_context():
        cliente_id, slug, producto_id = _preparar_tienda('bi05-consent-pendiente')
        registrar_casilla(cliente_id, '0981 620 001', False)
        assert contar_sin_marcar(cliente_id) == 1
    try:
        respuesta = _pedido_tienda(client, slug, producto_id, '0981 620 001', acepta_mensajes=True)
        assert respuesta.status_code == 201
        with app.app_context():
            assert contar_sin_marcar(cliente_id) == 0
            assert telefonos_con_consentimiento(cliente_id) == {'+595981620001'}
    finally:
        _restaurar_modo(app)
