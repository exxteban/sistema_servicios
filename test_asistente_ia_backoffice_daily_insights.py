from app.services.ia_backoffice.daily_insights import generar_insights_diarios
from app import create_app
from app.routes.insights_diarios import _agregar_enlaces


def test_daily_insights_usa_payload_de_tools(monkeypatch):
    calls = []

    def fake_tool(nombre, argumentos, usuario=None):
        calls.append((nombre, argumentos))
        if nombre == 'ventas_top_productos':
            return {
                'ok': True,
                'data': {
                    'productos': [{
                        'nombre': 'Cargador Tipo C',
                        'unidades': 12,
                        'ingreso': 360000,
                    }],
                },
            }
        return {'ok': True, 'data': {}}

    monkeypatch.setattr('app.services.ia_backoffice.daily_insights.ejecutar_tool_backoffice', fake_tool)

    resultado = generar_insights_diarios(usuario=None, usar_ia=False)

    assert ('ventas_top_productos', {'periodo': '7d', 'top_n': 3}) in calls
    assert ('inventario_productos_baja_rotacion', {'periodo': '30d', 'top_n': 3}) in calls
    assert resultado['generado_por'] == 'tools'
    assert resultado['insights'][0]['source_tool'] == 'ventas_top_productos'
    assert 'Cargador Tipo C' in resultado['insights'][0]['texto']
    assert '12 unidades' in resultado['insights'][0]['texto']


def test_daily_insights_no_inventa_si_no_hay_datos(monkeypatch):
    def fake_tool(nombre, argumentos, usuario=None):
        return {'ok': True, 'data': {}}

    monkeypatch.setattr('app.services.ia_backoffice.daily_insights.ejecutar_tool_backoffice', fake_tool)

    resultado = generar_insights_diarios(usuario=None, usar_ia=False)

    assert len(resultado['insights']) == 1
    assert resultado['insights'][0]['tipo'] == 'sin_datos_suficientes'
    assert 'no encontraron datos suficientes' in resultado['insights'][0]['texto']


def test_daily_insights_recomienda_ofertar_productos_sin_movimiento(monkeypatch):
    def fake_tool(nombre, argumentos, usuario=None):
        if nombre == 'inventario_productos_baja_rotacion':
            return {
                'ok': True,
                'data': {
                    'periodo_label': 'ultimos 30 dias',
                    'productos': [{
                        'nombre': 'Funda Modelo Viejo',
                        'stock_actual': 18,
                        'unidades_periodo': 0,
                        'valor_stock_costo': 540000,
                        'clasificacion': 'producto_muerto',
                        'accion_recomendada': 'Ofertar o rematar para liberar capital inmovilizado.',
                    }],
                },
            }
        return {'ok': True, 'data': {}}

    monkeypatch.setattr('app.services.ia_backoffice.daily_insights.ejecutar_tool_backoffice', fake_tool)

    resultado = generar_insights_diarios(usuario=None, usar_ia=False)

    insight = resultado['insights'][0]
    assert insight['tipo'] == 'producto_baja_rotacion'
    assert insight['source_tool'] == 'inventario_productos_baja_rotacion'
    assert 'Funda Modelo Viejo' in insight['texto']
    assert 'vendio 0' in insight['texto']
    assert 'Ofertar o rematar' in insight['accion_sugerida']


def test_daily_insights_agrega_enlace_a_falla_frecuente():
    app = create_app('testing')
    payload = {
        'insights': [{
            'source_tool': 'reparaciones_fallas_frecuentes',
            'source_payload': {
                'data': {
                    'fallas': [{'falla': 'CAMBIO DE DISPLAY'}],
                },
            },
        }],
    }

    with app.test_request_context('/'):
        _agregar_enlaces(payload)

    enlace = payload['insights'][0]['enlace']
    assert enlace['url'] == '/reparaciones/?q=CAMBIO+DE+DISPLAY'
    assert enlace['label'] == 'Ver reparaciones filtradas'
