from uuid import uuid4

from app import create_app, db
from app.models import AsistenteIABackofficeAudit, Configuracion, Rol, Usuario
from app.services.ia_backoffice.acciones import preparar_accion_asistida, preparar_accion_desde_chat
from app.services.ia_backoffice.settings import (
    CLAVE_ASSISTED_ACTIONS_ENABLED,
    CLAVE_READONLY_MODE,
    obtener_configuracion_asistente,
)


def _loguear(client, user_id):
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def test_sprint9_acciones_asistidas_quedan_deshabilitadas_por_defecto():
    app = create_app('testing')

    with app.app_context():
        cfg = obtener_configuracion_asistente()
        assert cfg.assisted_actions_enabled is False

        admin = Usuario.query.filter_by(username='admin').first()
        resultado = preparar_accion_asistida(
            'recordatorio_interno',
            {'titulo': 'Llamar clientes dormidos'},
            admin,
        )

        assert resultado['ok'] is False
        assert resultado['error'] == 'acciones_asistidas_deshabilitadas'


def test_sprint9_prepara_borrador_confirmable_y_lo_audita_sin_ejecutar():
    app = create_app('testing')

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_ASSISTED_ACTIONS_ENABLED, True)
        admin = Usuario.query.filter_by(username='admin').first()

        resultado = preparar_accion_asistida(
            'borrador_campanha',
            {
                'titulo': 'Recuperar clientes de abril',
                'objetivo': 'Contactar clientes valiosos dormidos',
                'mensaje': 'Hola, tenemos opciones nuevas para vos.',
                'destinatarios': ['Cliente A', 'Cliente B'],
            },
            admin,
        )

        assert resultado['ok'] is True
        accion = resultado['accion']
        assert accion['requiere_confirmacion'] is True
        assert accion['ejecutada'] is False
        assert accion['modo'] == 'solo_borrador'
        assert accion['readonly_mode'] is True
        assert accion['payload']['mensaje_borrador'] == 'Hola, tenemos opciones nuevas para vos.'

        audit = db.session.get(AsistenteIABackofficeAudit, accion['id_accion'])
        assert audit is not None
        assert audit.estado == 'accion_preparada'
        assert audit.username == admin.username
        assert 'accion_asistida_preparar' in audit.tools_usadas


def test_sprint9_acciones_asistidas_exigen_modo_solo_lectura():
    app = create_app('testing')

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_ASSISTED_ACTIONS_ENABLED, True)
        Configuracion.establecer_bool(CLAVE_READONLY_MODE, False)
        admin = Usuario.query.filter_by(username='admin').first()

        resultado = preparar_accion_asistida(
            'recordatorio_interno',
            {'titulo': 'Revisar cierres pendientes'},
            admin,
        )

        assert resultado['ok'] is False
        assert resultado['error'] == 'modo_solo_lectura_requerido'


def test_sprint9_chat_solo_infiere_accion_con_pedido_explicito():
    app = create_app('testing')

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_ASSISTED_ACTIONS_ENABLED, True)
        admin = Usuario.query.filter_by(username='admin').first()

        normal = preparar_accion_desde_chat(
            'Como van mis ventas este mes?',
            'Tus ventas subieron 10%.',
            admin,
        )
        accion = preparar_accion_desde_chat(
            'Preparame un reporte descargable de ventas del mes',
            'Resumen de ventas del mes.',
            admin,
        )

        assert normal is None
        assert accion is not None
        assert accion['tipo'] == 'reporte_descargable'
        assert accion['requiere_confirmacion'] is True
        assert accion['ejecutada'] is False


def test_sprint9_endpoints_preparan_y_confirman_sin_mutaciones_automaticas():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_ASSISTED_ACTIONS_ENABLED, True)
        admin = Usuario.query.filter_by(username='admin').first()
        admin_id = admin.id_usuario

    _loguear(client, admin_id)
    csrf = client.get('/auth/csrf').get_json()['csrf_token']
    response = client.post(
        '/asistente-ia/api/acciones/preparar',
        json={
            'tipo': 'recordatorio_interno',
            'payload': {
                'titulo': 'Revisar pagos pendientes',
                'fecha_sugerida': '2026-04-28',
                'responsable': 'admin',
            },
        },
        headers={'X-CSRFToken': csrf},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data['ok'] is True
    assert data['accion']['ejecutada'] is False
    id_accion = data['accion']['id_accion']

    response = client.post(
        f'/asistente-ia/api/acciones/{id_accion}/confirmar',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data['ok'] is True
    assert data['estado'] == 'accion_confirmada_sin_ejecucion'

    with app.app_context():
        confirmado = AsistenteIABackofficeAudit.query.filter_by(
            estado='accion_confirmada_sin_ejecucion',
        ).order_by(AsistenteIABackofficeAudit.id_audit.desc()).first()
        assert confirmado is not None
        assert confirmado.username == 'admin'


def test_sprint9_api_chat_devuelve_tarjeta_accion_confirmable_sin_llamar_ia_real():
    import app.routes.asistente_ia as route_module

    app = create_app('testing')
    client = app.test_client()
    original = route_module.generar_respuesta_backoffice

    def fake_generar(_historial, _usuario, resumen_historial=''):
        return {
            'contenido': 'Reporte preparado como borrador. Falta confirmacion explicita.',
            'estado': 'ok',
            'modelo': 'test',
            'provider': 'test',
        }

    try:
        route_module.generar_respuesta_backoffice = fake_generar
        with app.app_context():
            Configuracion.establecer_bool(CLAVE_ASSISTED_ACTIONS_ENABLED, True)
            admin = Usuario.query.filter_by(username='admin').first()
            admin_id = admin.id_usuario

        _loguear(client, admin_id)
        csrf = client.get('/auth/csrf').get_json()['csrf_token']
        response = client.post(
            '/asistente-ia/api/chat',
            json={'mensaje': 'Generame una lista de clientes para contactar'},
            headers={'X-CSRFToken': csrf},
        )
    finally:
        route_module.generar_respuesta_backoffice = original

    assert response.status_code == 200
    data = response.get_json()
    assert data['ok'] is True
    assert data['accion']['tipo'] == 'lista_clientes_contactar'
    assert data['accion']['requiere_confirmacion'] is True
    assert data['accion']['ejecutada'] is False


def test_sprint9_confirmar_accion_de_otro_usuario_requiere_mismo_usuario_o_root():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_ASSISTED_ACTIONS_ENABLED, True)
        admin = Usuario.query.filter_by(username='admin').first()
        rol = Rol.query.filter_by(nombre='Administrador').first()
        otro = Usuario(
            username=f'admin_accion_ia_{uuid4().hex[:6]}',
            nombre_completo='Admin Accion IA',
            id_rol=rol.id_rol,
            activo=True,
        )
        otro.set_password('1234')
        db.session.add(otro)
        db.session.commit()

        accion = preparar_accion_asistida('reporte_descargable', {'titulo': 'Ventas mes'}, admin)
        admin_id = admin.id_usuario
        otro_id = otro.id_usuario
        id_accion = accion['accion']['id_accion']

    _loguear(client, otro_id)
    csrf = client.get('/auth/csrf').get_json()['csrf_token']
    response = client.post(
        f'/asistente-ia/api/acciones/{id_accion}/confirmar',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 403
    assert response.get_json()['error'] == 'sin_permiso_accion'

    _loguear(client, admin_id)
    response = client.post(
        f'/asistente-ia/api/acciones/{id_accion}/confirmar',
        json={},
        headers={'X-CSRFToken': csrf},
    )
    assert response.status_code == 200
