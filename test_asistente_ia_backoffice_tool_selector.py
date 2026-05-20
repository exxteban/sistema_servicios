from datetime import date

from app import create_app
from app.models import Configuracion, Usuario
from app.services.ia_backoffice.context import construir_contexto_minimo
from app.services.ia_backoffice.response_engine import (
    _respuesta_directa_tool,
    _respuesta_resumen_tools_textuales,
    _tool_calls_textuales,
    generar_respuesta_backoffice,
)
from app.services.ia_backoffice.settings import CLAVE_ENABLED
from app.services.ia_backoffice.temporal_args import normalizar_argumentos_temporales
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.tool_selector import (
    nombres_tools_relevantes,
    seleccionar_tools_backoffice,
)
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS


def _nombres(tools):
    return [tool['function']['name'] for tool in tools]


def test_selector_reduce_catalogo_para_consulta_de_ventas():
    historial = [{'role': 'user', 'content': 'Que producto se vendio mas entre enero y marzo?'}]

    nombres = nombres_tools_relevantes(historial)

    assert 'ventas_top_productos' in nombres
    assert 'ventas_resumen_periodo' in nombres
    assert 'caja_cierre_detalle' not in nombres
    assert len(nombres) < len(BACKOFFICE_TOOLS)


def test_selector_prioriza_tool_consejera_para_crecimiento():
    historial = [{'role': 'user', 'content': 'que puedo hacer para vender mas?'}]

    nombres = nombres_tools_relevantes(historial)

    assert nombres[0] == 'ventas_recomendaciones_crecimiento'
    assert len(nombres) < len(BACKOFFICE_TOOLS)


def test_selector_usa_contexto_reciente_en_followup_de_producto():
    historial = [
        {'role': 'user', 'content': 'Que tipos de celulares hay?'},
        {'role': 'assistant', 'content': 'Encontre celulares Samsung y iPhone.'},
        {'role': 'user', 'content': 'De color blanco no hay?'},
    ]

    nombres = nombres_tools_relevantes(historial)

    assert 'buscar_entidad_backoffice' in nombres
    assert 'producto_detalle_360' in nombres
    assert 'inventario_resumen' in nombres


def test_selector_no_envia_todas_las_tools_para_caja():
    historial = [{'role': 'user', 'content': 'Hubo faltante en el cierre de caja de hoy?'}]

    nombres = _nombres(seleccionar_tools_backoffice(historial))

    assert 'caja_cierre_diferencia' in nombres
    assert 'caja_estado_actual' in nombres
    assert 'tienda_resumen_analytics' not in nombres
    assert len(nombres) < len(BACKOFFICE_TOOLS)


def test_contexto_temporal_ancla_hoy_y_ultimos_dos_meses(monkeypatch):
    app = create_app('testing')
    monkeypatch.setattr('app.services.ia_backoffice.context.today_local', lambda: date(2026, 4, 27))

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        contexto = construir_contexto_minimo(admin)

    tiempo = contexto['tiempo']
    assert tiempo['fecha_actual_local'] == '2026-04-27'
    assert tiempo['anio_actual'] == 2026
    assert tiempo['rangos_referencia']['ultimos_2_meses_desde_hoy'] == {
        'periodo': 'custom',
        'desde': '2026-02-27',
        'hasta': '2026-04-27',
    }


def test_normalizador_temporal_corrige_ultimos_meses_desde_hoy(monkeypatch):
    monkeypatch.setattr('app.services.ia_backoffice.temporal_args.today_local', lambda: date(2026, 4, 27))

    args = normalizar_argumentos_temporales(
        {'periodo': 'custom', 'desde': '2025-05-16', 'hasta': '2025-07-16'},
        'y los que se vendieron en 2 meses desde hoy',
    )

    assert args['periodo'] == 'custom'
    assert args['desde'] == '2026-02-27'
    assert args['hasta'] == '2026-04-27'


def test_parser_dsml_textual_soporta_formato_con_parametros_y_alias():
    contenido = '''
< | DSML | tool_calls>
< | DSML | invoke name="clientes_a_recuperar">
< | DSML | parameter name="top_n" string="false">5</ | DSML | parameter>
</ | DSML | invoke>
</ | DSML | tool_calls>
'''

    calls = _tool_calls_textuales(contenido)

    assert len(calls) == 1
    assert calls[0].function.name == 'clientes_para_contactar'
    assert '"top_n": 5' in calls[0].function.arguments


def test_resumen_textual_no_expone_dsml_crudo():
    respuesta = _respuesta_resumen_tools_textuales([
        {'tool': 'comparar_periodos_negocio'},
        {'tool': 'inventario_productos_reponer'},
    ])

    assert 'DSML' not in respuesta
    assert 'comparar_periodos_negocio' in respuesta


def test_respuesta_directa_recomendaciones_crecimiento_formatea_consejo():
    respuesta = _respuesta_directa_tool('ventas_recomendaciones_crecimiento', {
        'ok': True,
        'data': {
            'periodo_label': 'Ultimos 30 dias',
            'metricas': {'total_ventas': 1000000, 'cantidad_ventas': 4, 'ticket_promedio': 250000, 'margen_bruto_pct': 32.5},
            'recomendaciones': [{'accion': 'Impulsar producto estrella', 'motivo': 'Ya probo demanda.'}],
        },
    })

    assert 'Para vender mas' in respuesta
    assert 'Impulsar producto estrella' in respuesta


def test_tool_consejera_crecimiento_esta_registrada_y_ejecuta():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        respuesta = ejecutar_tool_backoffice(
            'ventas_recomendaciones_crecimiento',
            {'periodo': '30d', 'top_n': 3},
            usuario=admin,
        )

    assert respuesta['ok'] is True
    assert 'recomendaciones' in respuesta['data']
    assert respuesta['data']['nota'].startswith('Diagnostico comercial')


def test_selector_prioriza_tools_de_metricas_para_ganancia_neta_vs_caja():
    historial = [{'role': 'user', 'content': 'Cual es la diferencia entre ganancia neta y resultado de caja?'}]

    nombres = nombres_tools_relevantes(historial)

    assert 'metricas_comparacion_negocio' in nombres
    assert 'metricas_explicacion_negocio' in nombres
    assert 'metricas_resumen_operativo' in nombres


def test_selector_prioriza_tool_de_fidelizacion_para_el_modulo():
    historial = [{'role': 'user', 'content': 'Como funciona el modulo de fidelizacion?'}]

    nombres = nombres_tools_relevantes(historial)

    assert 'fidelizacion_resumen' in nombres
    assert 'modulo_funcionamiento' in nombres
    assert len(nombres) < len(BACKOFFICE_TOOLS)


def test_selector_prioriza_tool_generica_para_explicar_modulo():
    historial = [{'role': 'user', 'content': 'Como funciona el modulo de ventas?'}]

    nombres = nombres_tools_relevantes(historial)

    assert 'modulo_funcionamiento' in nombres


def test_selector_activa_tools_clientes_en_consulta_de_listado():
    historial = [{'role': 'user', 'content': 'Que clientes tienen fidelizacion ahora?'}]

    nombres = nombres_tools_relevantes(historial)

    assert 'clientes_top_valor' in nombres
    assert 'clientes_para_contactar' in nombres
    assert 'fidelizacion_resumen' in nombres


def test_respuesta_directa_fidelizacion_formatea_resumen_natural():
    respuesta = _respuesta_directa_tool('fidelizacion_resumen', {
        'ok': True,
        'data': {
            'activa': True,
            'regla': {
                'compras_requeridas': 3,
                'compras_ventana_dias': 365,
                'premios_por_objetivo': 1,
                'modo_generacion_label': 'Acumulativo: cada X compras genera Y beneficios',
            },
            'beneficio': {
                'resumen': '10% de descuento',
                'vigencia_dias': 30,
                'pos_aplicable': True,
            },
            'metricas': {
                'clientes_con_saldo': 4,
                'beneficios_disponibles_total': 7,
            },
            'clientes': [
                {
                    'id_cliente': 10,
                    'nombre': 'Maria',
                    'compras_acumuladas': 2,
                    'beneficios_disponibles': 1,
                },
            ],
            'flujo': ['Cada venta suma una compra.', 'Al llegar a la meta se libera el beneficio.'],
        },
    })

    assert 'Fidelizacion activa' in respuesta
    assert 'Beneficio actual: 10% de descuento.' in respuesta
    assert 'Uso en POS: si' in respuesta
    assert 'Clientes con saldo/historial (muestra):' in respuesta


def test_respuesta_directa_modulo_funcionamiento_formatea_sin_codigo():
    respuesta = _respuesta_directa_tool('modulo_funcionamiento', {
        'ok': True,
        'data': {
            'encontrado': True,
            'label': 'Ventas',
            'summary': 'Gestiona el registro de ventas, descuentos, credito y cierre comercial de cada operacion.',
            'funciones_clave': ['Permite realizar ventas', 'Permite anular ventas completadas'],
            'flujo_resumen': ['Se cargan productos y condiciones.', 'La venta puede pasar a caja.'],
            'acciones_sensibles': ['Permite anular ventas completadas'],
        },
    })

    assert 'Ventas:' in respuesta
    assert 'Que se puede hacer:' in respuesta
    assert 'Como se usa normalmente:' in respuesta
    assert 'codigo fuente' not in respuesta.lower()


def test_tool_fidelizacion_esta_registrada_y_ejecuta():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        respuesta = ejecutar_tool_backoffice('fidelizacion_resumen', {}, usuario=admin)

    assert respuesta['ok'] is True
    assert 'regla' in respuesta['data']
    assert 'beneficio' in respuesta['data']
    assert 'metricas' in respuesta['data']


def test_tool_modulo_funcionamiento_esta_registrada_y_ejecuta():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        respuesta = ejecutar_tool_backoffice('modulo_funcionamiento', {'modulo': 'ventas'}, usuario=admin)

    assert respuesta['ok'] is True
    assert respuesta['data']['encontrado'] is True
    assert respuesta['data']['modulo'] == 'ventas'
    assert respuesta['data']['funciones_clave']


def test_respuesta_directa_fidelizacion_sale_sin_llamar_modelo():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        Configuracion.establecer_bool(CLAVE_ENABLED, True)
        respuesta = generar_respuesta_backoffice(
            [{'role': 'user', 'content': 'La fidelizacion esta activa y que beneficio da?'}],
            admin,
        )

    assert respuesta['estado'] == 'ok'
    assert respuesta['tools_usadas'] == ['fidelizacion_resumen']
    assert 'Fidelizacion' in respuesta['contenido']


def test_respuesta_directa_modulo_general_sale_sin_llamar_modelo():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        Configuracion.establecer_bool(CLAVE_ENABLED, True)
        respuesta = generar_respuesta_backoffice(
            [{'role': 'user', 'content': 'Como funciona el modulo de ventas?'}],
            admin,
        )

    assert respuesta['estado'] == 'ok'
    assert respuesta['tools_usadas'] == ['modulo_funcionamiento']
    assert 'Ventas:' in respuesta['contenido']


def test_respuesta_directa_modulo_caja_para_que_sirve_prioriza_explicacion_funcional():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        Configuracion.establecer_bool(CLAVE_ENABLED, True)
        respuesta = generar_respuesta_backoffice(
            [{'role': 'user', 'content': 'Modulo de caja para que sirve y como se usa?'}],
            admin,
        )

    assert respuesta['estado'] == 'ok'
    assert respuesta['tools_usadas'] == ['modulo_funcionamiento']
    assert 'Caja:' in respuesta['contenido']


def test_followup_reutiliza_modulo_anterior_en_pregunta_generica():
    app = create_app('testing')

    with app.app_context():
        admin = Usuario.query.filter_by(username='admin').first()
        Configuracion.establecer_bool(CLAVE_ENABLED, True)
        respuesta = generar_respuesta_backoffice(
            [
                {'role': 'user', 'content': 'Como funciona el modulo de fidelizacion?'},
                {'role': 'assistant', 'content': 'Resumen previo.'},
                {'role': 'user', 'content': 'pero como funciona el modulo?'},
            ],
            admin,
        )

    assert respuesta['estado'] == 'ok'
    assert respuesta['tools_usadas'] == ['modulo_funcionamiento']
    assert 'Fidelizacion:' in respuesta['contenido']
