"""El Asistente IA de arriba ve los platos vendidos en gastronomia (guardados como servicio, no como producto)."""
from flask_login import login_user

from app import create_app, db
from app.models import Usuario
from app.services.ia_backoffice.tool_cache import limpiar_tool_cache
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from gastronomia.models import GastronomiaProducto
from test_gastronomia_reportes import _abrir_caja, _crear_insumo_receta, _crear_productos, _csrf, _loguear, _pedido_cobrado


def _venta_de_hoy(nombre: str, username: str):
    app = create_app('testing')
    client = app.test_client()
    cliente_id, pizza_id, bebida_id = _crear_productos(app, nombre, username)
    _crear_insumo_receta(app, cliente_id, pizza_id, nombre=f'Muzza {username}', stock=10, cantidad=1, precio_compra=10000)
    with app.app_context():
        db.session.get(GastronomiaProducto, pizza_id).costo_extra = 2000
        db.session.commit()
    _loguear(client, app, username)
    _abrir_caja(app, username)
    csrf = _csrf(client.get('/gastronomia/caja').get_data(as_text=True))
    _pedido_cobrado(client, csrf, [{'producto_id': pizza_id, 'cantidad': 2}, {'producto_id': bebida_id, 'cantidad': 1}])
    return app


def _tool(app, username, nombre, args):
    with app.test_request_context():
        usuario = Usuario.query.filter_by(username=username).first()
        login_user(usuario)
        try:
            limpiar_tool_cache()
        except Exception:  # noqa: BLE001 - la cache es opcional en tests
            pass
        resultado = ejecutar_tool_backoffice(nombre, args, usuario=usuario)
    assert resultado['ok'], resultado
    return resultado['data']


def test_ranking_rentabilidad_categorias_y_ganancia_incluyen_platos():
    app = _venta_de_hoy('Resto Arriba', 'resto_arriba')

    top = _tool(app, 'resto_arriba', 'ventas_top_productos', {'periodo': 'hoy'})
    assert [(p['nombre'], p['unidades'], p['ingreso']) for p in top['productos']] == [('Pizza', 2, 80000.0), ('Bebida', 1, 10000.0)]

    rentables = _tool(app, 'resto_arriba', 'ventas_rentabilidad_productos', {'periodo': 'hoy'})['productos']
    pizza = next(p for p in rentables if p['nombre'] == 'Pizza')
    assert pizza['costo_estimado'] == 24000 and pizza['ganancia_estimada'] == 56000 and pizza['margen_pct'] == 70.0
    assert next(p for p in rentables if p['nombre'] == 'Bebida')['sin_costo_cargado'] is True

    bajo = _tool(app, 'resto_arriba', 'ventas_productos_bajo_margen', {'periodo': 'hoy'})['productos']
    assert bajo[0]['nombre'] == 'Pizza'  # 70% contra 100% de la bebida sin costo

    categorias = _tool(app, 'resto_arriba', 'ventas_por_categoria', {'periodo': 'hoy'})['categorias']
    assert categorias[0]['categoria'] == 'Reportes' and categorias[0]['ingreso'] == 90000 and categorias[0]['participacion_pct'] == 100

    ganancia = _tool(app, 'resto_arriba', 'ventas_ganancia_periodo', {'periodo': 'hoy'})
    assert ganancia['total_ventas'] == 90000 and ganancia['costo_estimado'] == 24000
    assert ganancia['ganancia_bruta_estimada'] == 66000 and ganancia['productos_sin_costo'] == 1
    assert ganancia['margen_bruto_pct'] == round(66000 / 90000 * 100, 2)


def test_tool_sin_adaptador_no_cambia():
    from app.services.ia_backoffice.ventas_tools import ventas_resumen_periodo

    app = _venta_de_hoy('Resto Arriba Dos', 'resto_arriba_dos')
    resumen = _tool(app, 'resto_arriba_dos', 'ventas_resumen_periodo', {'periodo': 'hoy'})
    with app.app_context():
        assert resumen == ventas_resumen_periodo({'periodo': 'hoy'})
