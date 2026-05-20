from app import create_app, db
from app.models import PublicidadAdsEvento, Usuario


def _loguear(client, app, username: str):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        assert usuario is not None
        user_id = usuario.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def test_evento_publicidad_ads_se_registra_sin_login():
    app = create_app('testing')
    client = app.test_client()

    response = client.post(
        '/api/publicidad-ads/evento',
        json={
            'landing': 'publicidad_ads',
            'event_type': 'page_view',
            'label': 'landing_open',
            'section_id': 'inicio',
            'path': '/publicidad-ads/',
            'session_id': 'session-test-publicidad',
            'utm_source': 'google',
            'utm_campaign': 'ads-demo',
            'meta': {'scroll': '0'},
        },
        headers={
            'User-Agent': 'pytest-publicidad-ads',
            'Referer': 'https://example.com/anuncio',
        },
    )

    assert response.status_code == 202

    with app.app_context():
        evento = (
            PublicidadAdsEvento.query
            .filter_by(session_hash='session-test-publicidad')
            .order_by(PublicidadAdsEvento.id_evento.desc())
            .first()
        )
        assert evento is not None
        assert evento.tipo_evento == 'page_view'
        assert evento.utm_source == 'google'
        assert evento.utm_campaign == 'ads-demo'
        assert evento.visitante_hash


def test_panel_publicidad_ads_restringido_para_admin_no_root():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, app, 'admin')

    response = client.get('/publicidad-ads/admin')
    assert response.status_code == 403


def test_panel_publicidad_ads_permite_usuario_root():
    app = create_app('testing')
    client = app.test_client()
    _loguear(client, app, 'root')

    response = client.get('/publicidad-ads/admin')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Mini Analytics privado de la landing' in html
