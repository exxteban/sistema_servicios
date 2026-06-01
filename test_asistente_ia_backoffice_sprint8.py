from datetime import datetime
from uuid import uuid4

from app import create_app, db
from app.models import Configuracion, Rol, Usuario
from app.services.ia_backoffice.audit import (
    obtener_consumo_tokens,
    obtener_consumo_tokens_por_usuario,
    registrar_interaccion,
)
from app.services.ia_backoffice.history import compactar_historial
from app.services.ia_backoffice.limits import validar_presupuesto_tokens
from app.services.ia_backoffice.response_engine import generar_respuesta_backoffice
from app.services.ia_backoffice.settings import (
    CLAVE_DAILY_TOKEN_BUDGET,
    CLAVE_ENABLED,
    CLAVE_MAX_TOKENS,
    CLAVE_MONTHLY_TOKEN_BUDGET,
)
from app.services.ia_backoffice.tool_cache import limpiar_tool_cache
from app.services.ia_backoffice.tool_handlers import BACKOFFICE_TOOL_HANDLERS, ejecutar_tool_backoffice


def _loguear(client, user_id):
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def test_sprint8_cache_reutiliza_resultado_por_usuario_y_argumentos():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        assert admin is not None
        limpiar_tool_cache()
        original = BACKOFFICE_TOOL_HANDLERS['ventas_resumen_periodo']
        llamadas = {'cantidad': 0}

        def handler_fake(args, usuario=None):
            llamadas['cantidad'] += 1
            return {'contador': llamadas['cantidad'], 'periodo': args.get('periodo')}

        BACKOFFICE_TOOL_HANDLERS['ventas_resumen_periodo'] = handler_fake
        try:
            args = {'periodo': 'mes'}
            primera = ejecutar_tool_backoffice('ventas_resumen_periodo', args, usuario=admin)
            segunda = ejecutar_tool_backoffice('ventas_resumen_periodo', args, usuario=admin)
            tercera = ejecutar_tool_backoffice('ventas_resumen_periodo', {'periodo': '7d'}, usuario=admin)
        finally:
            BACKOFFICE_TOOL_HANDLERS['ventas_resumen_periodo'] = original
            limpiar_tool_cache()

        assert primera['ok'] is True
        assert segunda['data'] == primera['data']
        assert llamadas['cantidad'] == 2


def test_sprint8_cache_no_comparte_resultados_entre_usuarios():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        rol = Rol.query.filter_by(nombre='Administrador').first()
        usuario = Usuario(
            username=f'admin_cache_ia_{uuid4().hex[:6]}',
            nombre_completo='Admin Cache IA',
            id_rol=rol.id_rol,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.commit()

        limpiar_tool_cache()
        original = BACKOFFICE_TOOL_HANDLERS['ventas_resumen_periodo']
        llamadas = {'cantidad': 0}

        def handler_fake(args, usuario=None):
            llamadas['cantidad'] += 1
            return {'contador': llamadas['cantidad'], 'usuario': usuario.username}

        BACKOFFICE_TOOL_HANDLERS['ventas_resumen_periodo'] = handler_fake
        try:
            args = {'periodo': 'mes'}
            primera = ejecutar_tool_backoffice('ventas_resumen_periodo', args, usuario=admin)
            segunda = ejecutar_tool_backoffice('ventas_resumen_periodo', args, usuario=usuario)
            tercera = ejecutar_tool_backoffice('ventas_resumen_periodo', args, usuario=admin)
        finally:
            BACKOFFICE_TOOL_HANDLERS['ventas_resumen_periodo'] = original
            limpiar_tool_cache()

        assert primera['data']['contador'] == 1
        assert segunda['data']['contador'] == 2
        assert tercera['data']['contador'] == 1
        assert llamadas['cantidad'] == 2


def test_sprint8_metricas_de_tokens_agregan_por_periodo_y_usuario():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        root = Usuario.query.filter_by(username='root').first()
        inicio = datetime(2030, 1, 1, 0, 0, 0)
        fin = datetime(2030, 1, 2, 0, 0, 0)

        audit_admin = registrar_interaccion(
            admin,
            'Pregunta admin',
            'Respuesta admin',
            tokens_prompt=10,
            tokens_completion=15,
            commit=False,
        )
        audit_admin.fecha_hora = datetime(2030, 1, 1, 10, 0, 0)
        audit_root = registrar_interaccion(
            root,
            'Pregunta root',
            'Respuesta root',
            tokens_prompt=5,
            tokens_completion=7,
            commit=False,
        )
        audit_root.fecha_hora = datetime(2030, 1, 1, 11, 0, 0)
        db.session.commit()

        total = obtener_consumo_tokens(inicio, fin)
        solo_admin = obtener_consumo_tokens(inicio, fin, usuario=admin)
        por_usuario = obtener_consumo_tokens_por_usuario(inicio, fin)

        assert total['interacciones'] == 2
        assert total['tokens_total'] == 37
        assert solo_admin['interacciones'] == 1
        assert solo_admin['tokens_total'] == 25
        assert por_usuario[0]['tokens_total'] >= por_usuario[1]['tokens_total']
        assert {item['username'] for item in por_usuario} >= {'admin', 'root'}


def test_sprint8_presupuesto_diario_bloquea_cuando_consumo_mas_estimado_supera_limite():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        Configuracion.establecer_bool(CLAVE_ENABLED, True)
        Configuracion.establecer(CLAVE_DAILY_TOKEN_BUDGET, '20')
        Configuracion.establecer(CLAVE_MONTHLY_TOKEN_BUDGET, '0')
        Configuracion.establecer(CLAVE_MAX_TOKENS, '10')
        registrar_interaccion(
            admin,
            'Pregunta previa',
            'Respuesta previa',
            tokens_prompt=7,
            tokens_completion=8,
        )

        permitido, motivo = validar_presupuesto_tokens(10, usuario=admin)
        respuesta = generar_respuesta_backoffice([{'role': 'user', 'content': 'Como van mis ventas?'}], admin)

        assert permitido is False
        assert motivo == 'presupuesto_diario_excedido'
        assert respuesta['estado'] == 'presupuesto_diario_excedido'
        assert 'presupuesto diario' in respuesta['contenido']


def test_sprint8_presupuesto_mensual_bloquea_sin_api_key():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        Configuracion.establecer_bool(CLAVE_ENABLED, True)
        Configuracion.establecer(CLAVE_DAILY_TOKEN_BUDGET, '0')
        Configuracion.establecer(CLAVE_MONTHLY_TOKEN_BUDGET, '20')
        Configuracion.establecer(CLAVE_MAX_TOKENS, '10')
        registrar_interaccion(
            admin,
            'Pregunta mensual previa',
            'Respuesta mensual previa',
            tokens_prompt=12,
            tokens_completion=5,
        )

        respuesta = generar_respuesta_backoffice([{'role': 'user', 'content': 'Resumen de caja'}], admin)

        assert respuesta['estado'] == 'presupuesto_mensual_excedido'
        assert 'presupuesto mensual' in respuesta['contenido']


def test_sprint8_endpoint_consumo_es_solo_para_root_y_devuelve_metricas():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        root = Usuario.query.filter_by(username='root').first()
        admin = Usuario.query.filter_by(username='admin').first()
        Configuracion.establecer(CLAVE_DAILY_TOKEN_BUDGET, '1000')
        Configuracion.establecer(CLAVE_MONTHLY_TOKEN_BUDGET, '5000')
        registrar_interaccion(
            root,
            'Pregunta consumo',
            'Respuesta consumo',
            tokens_prompt=20,
            tokens_completion=30,
        )
        root_id = root.id_usuario
        admin_id = admin.id_usuario

    _loguear(client, admin_id)
    response = client.get('/asistente-ia/api/consumo')
    assert response.status_code == 403

    _loguear(client, root_id)
    response = client.get('/asistente-ia/api/consumo?top_n=5')
    assert response.status_code == 200
    data = response.get_json()

    assert data['ok'] is True
    assert data['daily_token_budget'] == 1000
    assert data['monthly_token_budget'] == 5000
    assert data['consumo_dia']['tokens_total'] >= 50
    assert data['consumo_mes']['tokens_total'] >= 50
    assert any(item['username'] == 'root' for item in data['usuarios_mes'])


def test_sprint8_endpoint_consumo_usuario_devuelve_solo_consumo_del_usuario_actual():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        root = Usuario.query.filter_by(username='root').first()
        Configuracion.establecer(CLAVE_DAILY_TOKEN_BUDGET, '100')
        registrar_interaccion(admin, 'Admin uso', 'Respuesta', tokens_prompt=10, tokens_completion=15)
        registrar_interaccion(root, 'Root uso', 'Respuesta', tokens_prompt=40, tokens_completion=20)
        admin_id = admin.id_usuario

    _loguear(client, admin_id)
    response = client.get('/asistente-ia/api/consumo-usuario')
    assert response.status_code == 200
    data = response.get_json()

    assert data['ok'] is True
    assert data['consumo_diario']['limite'] == 100
    assert data['consumo_diario']['usado'] == 25
    assert data['consumo_diario']['restante'] == 75


def test_sprint8_endpoint_historial_es_root_only_y_busca_consultas():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        root = Usuario.query.filter_by(username='root').first()
        admin = Usuario.query.filter_by(username='admin').first()
        registrar_interaccion(
            admin,
            'Necesito ventas de abril',
            'Resumen ventas abril',
            tokens_prompt=11,
            tokens_completion=13,
        )
        root_id = root.id_usuario
        admin_id = admin.id_usuario

    _loguear(client, admin_id)
    response = client.get('/asistente-ia/api/historial?q=abril&top_n=5')
    assert response.status_code == 200
    data = response.get_json()
    assert data['ok'] is True
    assert data['items']
    assert any('abril' in (item['pregunta_preview'] or '').lower() for item in data['items'])

    _loguear(client, root_id)
    response = client.get('/asistente-ia/api/historial?q=abril&top_n=5')
    assert response.status_code == 200


def test_sprint8_endpoint_historial_detalle_devuelve_interaccion_y_no_reanuda_chat():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        audit = registrar_interaccion(
            admin,
            'Consulta de prueba',
            'Respuesta de prueba',
            tools_usadas=['ventas_resumen_periodo'],
            tokens_prompt=3,
            tokens_completion=4,
        )
        audit_id = audit.id_audit
        admin_id = admin.id_usuario

    _loguear(client, admin_id)
    response = client.get(f'/asistente-ia/api/historial/{audit_id}')
    assert response.status_code == 200
    data = response.get_json()
    assert data['ok'] is True
    assert data['item']['pregunta'] == 'Consulta de prueba'
    assert data['item']['respuesta'] == 'Respuesta de prueba'
    assert data['item']['tools_usadas'] == ['ventas_resumen_periodo']
    assert data['item']['tokens_prompt'] == 3
    assert data['item']['tokens_completion'] == 4

    response = client.get('/asistente-ia/api/historial/999999')
    assert response.status_code == 404

    response = client.get(f'/asistente-ia/historial/{audit_id}')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Detalle completo del historial IA' in html
    assert 'Consulta de prueba' in html
    assert 'Respuesta de prueba' in html
    assert 'Tokens total' in html
    assert 'Prompt' in html


def test_sprint8_consumo_diario_se_renderiza_en_chat_y_panel_admin_es_root_only():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        root = Usuario.query.filter_by(username='root').first()
        admin = Usuario.query.filter_by(username='admin').first()
        root_id = root.id_usuario
        admin_id = admin.id_usuario

    _loguear(client, admin_id)
    response = client.get('/asistente-ia/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'ia-chat-usage' in html
    assert 'Consumo diario IA' in html
    assert 'caja y fidelización' in html
    assert 'ia-consumo-panel' not in html
    assert 'admin.js' not in html
    assert 'Panel IA' not in html
    assert 'Historial' in html
    assert '/asistente-ia/historial' in html
    response = client.get('/asistente-ia/admin')
    assert response.status_code in (302, 303)
    response = client.get('/asistente-ia/historial')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Historial de consultas' in html
    assert 'Solo lectura' in html
    assert 'Abrir en otra pestana' in html
    assert 'js/asistente_ia/historial.js' in html

    _loguear(client, root_id)
    response = client.get('/asistente-ia/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'ia-chat-usage' in html
    assert 'Consumo diario IA' in html
    assert 'caja y fidelización' in html
    assert 'ia-consumo-panel' not in html
    assert 'admin.js' not in html
    assert 'Panel IA' in html
    assert 'Historial' in html
    assert '/asistente-ia/admin' in html

    response = client.get('/asistente-ia/admin')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'ia-consumo-panel' in html
    assert 'Consumo hoy' in html
    assert 'js/asistente_ia/admin.js' in html

    response = client.get('/asistente-ia/historial')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Historial de consultas' in html
    assert 'Solo lectura' in html
    assert 'Abrir en otra pestana' in html
    assert 'js/asistente_ia/historial.js' in html


def test_sprint8_historial_renderiza_paginacion_optimizada():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        registrar_interaccion(
            admin,
            'Consulta paginacion historial',
            'Respuesta paginacion historial',
            tokens_prompt=11,
            tokens_completion=7,
            tools_usadas=['ventas_resumen_periodo'],
        )
        admin_id = admin.id_usuario

    _loguear(client, admin_id)
    response = client.get('/asistente-ia/historial')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'ia-historial-per-page' in html
    assert 'ia-historial-pages' in html
    assert 'ia-historial-total' in html
    assert 'ia-historial-detalle-link' in html

    response = client.get('/asistente-ia/api/historial?page=1&per_page=10')
    assert response.status_code == 200
    data = response.get_json()
    assert data['per_page'] == 10
    assert data['items'][0]['tokens_total'] >= 0
    assert 'tokens_prompt' in data['items'][0]
    assert 'tools_count' in data['items'][0]


def test_sprint8_api_chat_devuelve_consumo_diario_actualizado():
    import app.routes.asistente_ia as route_module

    app = create_app('testing')
    client = app.test_client()
    original = route_module.generar_respuesta_backoffice

    def fake_generar(_historial, _usuario, resumen_historial=''):
        return {
            'contenido': 'Respuesta con consumo medido.',
            'estado': 'ok',
            'modelo': 'test',
            'provider': 'test',
            'tokens_prompt': 10,
            'tokens_completion': 15,
        }

    try:
        route_module.generar_respuesta_backoffice = fake_generar
        with app.app_context():
            Configuracion.establecer_bool(CLAVE_ENABLED, True)
            Configuracion.establecer(CLAVE_DAILY_TOKEN_BUDGET, '100')
            Configuracion.establecer(CLAVE_MONTHLY_TOKEN_BUDGET, '0')
            admin = Usuario.query.filter_by(username='admin').first()
            admin_id = admin.id_usuario

        _loguear(client, admin_id)
        csrf = client.get('/auth/csrf').get_json()['csrf_token']
        response = client.post(
            '/asistente-ia/api/chat',
            json={'mensaje': 'Consulta consumo'},
            headers={'X-CSRFToken': csrf},
        )
    finally:
        route_module.generar_respuesta_backoffice = original

    assert response.status_code == 200
    data = response.get_json()
    assert data['consumo_diario']['limite'] == 100
    assert data['consumo_diario']['usado'] >= 25
    assert data['consumo_diario']['restante'] <= 75


def test_sprint8_compacta_historial_largo_en_resumen_de_sesion():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        Configuracion.establecer_bool(CLAVE_ENABLED, False)
        admin_id = admin.id_usuario

    _loguear(client, admin_id)
    csrf = client.get('/auth/csrf').get_json()['csrf_token']
    for indice in range(7):
        response = client.post(
            '/asistente-ia/api/chat',
            json={'mensaje': f'Pregunta larga de prueba {indice}'},
            headers={'X-CSRFToken': csrf},
        )
        assert response.status_code == 200

    with client.session_transaction() as sess:
        historial = sess.get('ia_backoffice_historial')
        resumen = sess.get('ia_backoffice_historial_resumen')
        assert len(historial) == 12
        assert resumen
        assert 'Pregunta larga de prueba 0' in resumen

    response = client.post('/asistente-ia/api/limpiar', json={}, headers={'X-CSRFToken': csrf})
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert not sess.get('ia_backoffice_historial')
        assert not sess.get('ia_backoffice_historial_resumen')


def test_sprint8_resumen_historial_respeta_limite_de_caracteres():
    mensajes = [
        {'role': 'user', 'content': 'consulta ' + ('x' * 500)},
        {'role': 'assistant', 'content': 'respuesta ' + ('y' * 500)},
    ]

    resumen = compactar_historial('previo ' + ('z' * 500), mensajes, max_chars=300)

    assert len(resumen) <= 300
    assert 'Asistente:' in resumen
