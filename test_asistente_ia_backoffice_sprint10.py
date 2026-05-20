import json

from app import create_app, db
from app.models import AsistenteIABackofficeAudit, Configuracion, Usuario
from app.services.ia_backoffice.context import construir_contexto_minimo
from app.services.ia_backoffice.response_engine import (
    _cfg_con_modelo_resuelto,
    _guia_tools_prioritarias,
    _mensajes,
    _respuesta_directa_tool,
)
from app.services.ia_backoffice.settings import (
    CLAVE_ADVANCED_MODEL_ENABLED,
    CLAVE_ASSISTED_ACTIONS_ENABLED,
    CLAVE_ENABLED,
    ConfiguracionAsistenteIA,
)


def _loguear(client, user_id):
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def test_sprint10_guia_prioriza_comparacion_y_drilldown_segun_consulta():
    guia = _guia_tools_prioritarias([
        {'role': 'user', 'content': 'Compara este mes vs el anterior y decime si algun cliente preocupa.'},
    ])

    assert 'comparar_periodos_negocio' in guia
    assert 'cliente_detalle_360' in guia


def test_sprint10_mensajes_inyectan_guia_de_tool_para_consulta_actual():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        mensajes = _mensajes(
            [{'role': 'user', 'content': 'Necesito el detalle de venta de la factura 001-001-0001234'}],
            admin,
        )

    assert mensajes[0]['role'] == 'system'
    assert 'detalle_venta_documento' in mensajes[0]['content']


def test_sprint10_contexto_minimo_refleja_tools_y_switches_reales():
    app = create_app('testing')

    with app.app_context():
        Configuracion.establecer_bool(CLAVE_ASSISTED_ACTIONS_ENABLED, True)
        Configuracion.establecer_bool(CLAVE_ADVANCED_MODEL_ENABLED, True)
        admin = Usuario.query.filter_by(username='admin').first()
        contexto = construir_contexto_minimo(admin)

    assert contexto['tools_habilitadas'] is True
    assert contexto['cantidad_tools'] > 0
    assert contexto['acciones_asistidas_habilitadas'] is True
    assert contexto['readonly_mode'] is True
    assert contexto['modelo_avanzado_habilitado'] is True


def test_sprint10_modelo_avanzado_solo_se_usa_en_consultas_complejas():
    cfg = ConfiguracionAsistenteIA(
        enabled=True,
        provider='deepseek',
        model='deepseek-v4-flash',
        deepseek_base_url='https://api.deepseek.com',
        max_tokens=700,
        temperature=0.3,
        daily_token_budget=0,
        monthly_token_budget=0,
        readonly_mode=True,
        assisted_actions_enabled=False,
        advanced_model_enabled=True,
        advanced_model='deepseek-v4-pro',
    )

    simple = _cfg_con_modelo_resuelto(cfg, [{'role': 'user', 'content': 'Cuanto vendi hoy?'}])
    complejo = _cfg_con_modelo_resuelto(cfg, [{'role': 'user', 'content': 'Analiza la rentabilidad y comparame contra el mes anterior'}])

    assert simple.model == 'deepseek-v4-flash'
    assert complejo.model == 'deepseek-v4-pro'


def test_sprint10_api_chat_audita_argumentos_y_resumen_de_tools():
    import app.routes.asistente_ia as route_module

    app = create_app('testing')
    client = app.test_client()
    original = route_module.generar_respuesta_backoffice

    def fake_generar(_historial, _usuario, resumen_historial=''):
        return {
            'contenido': 'Vendiste Gs. 10.000 hoy.',
            'estado': 'ok',
            'modelo': 'test-model',
            'provider': 'test',
            'tools_usadas': ['ventas_resumen_periodo'],
            'argumentos_normalizados': [
                {'tool': 'ventas_resumen_periodo', 'argumentos': {'periodo': 'hoy'}},
            ],
            'resultado_resumido': '[{"tool":"ventas_resumen_periodo","ok":true}]',
        }

    try:
        route_module.generar_respuesta_backoffice = fake_generar
        with app.app_context():
            Configuracion.establecer_bool(CLAVE_ENABLED, True)
            admin = Usuario.query.filter_by(username='admin').first()
            admin_id = admin.id_usuario

        _loguear(client, admin_id)
        csrf = client.get('/auth/csrf').get_json()['csrf_token']
        response = client.post(
            '/asistente-ia/api/chat',
            json={'mensaje': 'Como van las ventas hoy?'},
            headers={'X-CSRFToken': csrf},
        )
    finally:
        route_module.generar_respuesta_backoffice = original

    assert response.status_code == 200
    with app.app_context():
        audit = db.session.query(AsistenteIABackofficeAudit).order_by(
            AsistenteIABackofficeAudit.id_audit.desc(),
        ).first()
        assert audit is not None
        assert json.loads(audit.argumentos_normalizados)[0]['argumentos']['periodo'] == 'hoy'
        assert 'ventas_resumen_periodo' in audit.resultado_resumido


def test_sprint10_respuesta_directa_pide_seleccion_humana_si_hay_ambiguedad():
    texto = _respuesta_directa_tool(
        'cliente_detalle_360',
        {
            'ok': True,
            'data': {
                'encontrado': False,
                'requiere_seleccion': True,
                'candidatos': [
                    {'id_cliente': 12, 'nombre': 'Juan Perez', 'ruc_ci': '123', 'telefono': '0981'},
                    {'id_cliente': 44, 'nombre': 'Juan Pedro', 'ruc_ci': '456', 'telefono': '0982'},
                ],
            },
        },
    )

    assert 'Encontre varios clientes' in texto
    assert '12 | Juan Perez' in texto
    assert '44 | Juan Pedro' in texto


def test_sprint10_respuesta_directa_explica_no_encontrado_de_forma_util():
    texto = _respuesta_directa_tool(
        'producto_detalle_360',
        {
            'ok': True,
            'data': {
                'encontrado': False,
                'error': 'producto_no_encontrado',
            },
        },
    )

    assert texto == 'No encontre ese producto. Proba con nombre, codigo, codigo de barras o ID.'
