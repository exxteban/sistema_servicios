"""BI-04: materiales de activacion (enlace, QR y textos) para la lista de activacion (datos ficticios)."""
from app import create_app, db
from app.models.tienda import TiendaConfig
from gastronomia.services.bi.materiales import materiales_activacion
from test_gastronomia_bi_cola import _crear_negocio, _loguear


def _tienda(app, cliente_id: int, slug: str, activa: bool = True) -> None:
    with app.app_context():
        db.session.add(TiendaConfig(id_cliente=cliente_id, slug=slug, nombre_tienda='Pizzería BI', activa=activa))
        db.session.commit()


def test_sin_tienda_activa_no_hay_materiales():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI04 Sin Tienda', 'bi04_sin_tienda')
    _tienda(app, cliente_id, 'tienda-bi04-inactiva', activa=False)
    with app.test_request_context('/'):
        assert materiales_activacion(cliente_id) is None


def test_materiales_con_tienda_activa_traen_enlace_textos_y_qr():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI04 Materiales', 'bi04_materiales')
    _tienda(app, cliente_id, 'pizzeria-bi04')
    with app.test_request_context('/'):
        materiales = materiales_activacion(cliente_id)

    assert materiales['link'].endswith('/tienda/pizzeria-bi04')
    assert 'Pizzería BI' in materiales['bio']
    assert materiales['link'] in materiales['bio']
    assert materiales['link'] in materiales['estado_whatsapp']
    assert '<svg' in materiales['qr_svg']
    assert materiales['qr_descarga'].startswith('data:image/svg+xml;base64,')


def test_sin_libreria_qr_los_textos_y_el_enlace_siguen_disponibles(monkeypatch):
    def _sin_segno(*args, **kwargs):
        raise ImportError('segno no instalado')

    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'BI04 Sin QR', 'bi04_sin_qr')
    _tienda(app, cliente_id, 'tienda-bi04-sin-qr')
    monkeypatch.setattr('gastronomia.services.bi.materiales.generar_qr_svg', _sin_segno)
    with app.test_request_context('/'):
        materiales = materiales_activacion(cliente_id)

    assert materiales['link'].endswith('/tienda/tienda-bi04-sin-qr')
    assert materiales['bio']
    assert materiales['qr_svg'] == ''
    assert materiales['qr_descarga'] == ''


def test_tab_muestra_materiales_con_qr_descargable():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, _, _ = _crear_negocio(app, 'BI04 Tab Materiales', 'bi04_tab_materiales')
    _tienda(app, cliente_id, 'tienda-bi04-tab')
    _loguear(client, app, 'bi04_tab_materiales')

    html = client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)

    assert 'Materiales para publicar' in html
    assert 'Descargar QR (SVG)' in html
    assert 'Texto para la bio de Instagram' in html
    assert 'Texto para el estado de WhatsApp' in html
