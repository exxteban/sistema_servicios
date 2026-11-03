"""BI-04: embudo de la tienda online por plato (visitas, visitantes y pedidos web). Datos ficticios."""
from datetime import timedelta

from app import create_app, db
from app.models.tienda import TiendaConfig
from app.utils.helpers import today_local, utc_bounds_for_local_dates
from gastronomia.bi_models import GastronomiaTiendaVisita
from gastronomia.models import GastronomiaCategoria, GastronomiaProducto
from gastronomia.services.bi.embudo import embudo_platos, resumen_embudo_seguro
from test_gastronomia_bi_cola import _crear_negocio, _loguear, _pedido


def _periodo() -> dict:
    return {'desde': today_local() - timedelta(days=29), 'hasta': today_local()}


def _producto(app, cliente_id: int, nombre: str) -> int:
    with app.app_context():
        categoria = GastronomiaCategoria.query.filter_by(cliente_id=cliente_id).first()
        producto = GastronomiaProducto(
            cliente_id=cliente_id,
            categoria_id=categoria.id_categoria,
            nombre=nombre,
            precio=30000,
            disponible=True,
            visible=True,
            activo=True,
            publicado_tienda=True,
        )
        db.session.add(producto)
        db.session.commit()
        return producto.id_producto


def _visita(app, cliente_id: int, producto_id: int, visitante: str, dias_atras: int) -> None:
    dia = today_local() - timedelta(days=dias_atras)
    inicio_utc, _ = utc_bounds_for_local_dates(dia, dia)
    with app.app_context():
        db.session.add(GastronomiaTiendaVisita(
            cliente_id=cliente_id,
            producto_id=producto_id,
            visitante_hash=visitante,
            fecha_visita=inicio_utc + timedelta(hours=12),
        ))
        db.session.commit()


def _negocio_con_embudo(app, username: str):
    """Plato A: 6 visitantes sin pedidos web. Plato B: 6 visitantes y 2 pedidos web. Plato C: 2 visitantes.
    Plato A tambien tiene 10 visitas de hace 40 dias, fuera de la ventana."""
    cliente_id, usuario_id, _ = _crear_negocio(app, 'Embudo ' + username, username)
    plato_a = _producto(app, cliente_id, 'Plato A')
    plato_b = _producto(app, cliente_id, 'Plato B')
    plato_c = _producto(app, cliente_id, 'Plato C')
    for indice in range(6):
        _visita(app, cliente_id, plato_a, f'a{indice}', 2)
        _visita(app, cliente_id, plato_b, f'b{indice}', 2)
    for indice in range(2):
        _visita(app, cliente_id, plato_c, f'c{indice}', 2)
    for indice in range(10):
        _visita(app, cliente_id, plato_a, f'viejo{indice}', 40)
    _pedido(app, cliente_id, usuario_id, plato_b, 3, celular='0981 610 001', nombre='Web 1', origen='tienda_online')
    _pedido(app, cliente_id, usuario_id, plato_b, 1, celular='0981 610 002', nombre='Web 2', origen='tienda_online')
    return cliente_id, plato_a, plato_b, plato_c


def test_embudo_marca_platos_vistos_y_poco_pedidos_solo_con_evidencia():
    app = create_app('testing')
    cliente_id, plato_a, plato_b, plato_c = _negocio_con_embudo(app, 'bi04_embudo_base')
    with app.app_context():
        resultado = embudo_platos(cliente_id, _periodo())

    assert resultado['hay_visitas'] is True
    assert resultado['visitas'] == 14  # las 10 visitas de hace 40 dias no entran
    assert resultado['visitantes'] == 14
    assert resultado['pedidos_web'] == 2
    assert [plato['nombre'] for plato in resultado['atencion']] == ['Plato A']
    platos = {plato['nombre']: plato for plato in resultado['platos']}
    assert platos['Plato A']['evaluable'] is True and platos['Plato A']['poco_pedido'] is True
    assert platos['Plato B']['pedidos_web'] == 2 and platos['Plato B']['poco_pedido'] is False
    assert platos['Plato C']['evaluable'] is False and platos['Plato C']['poco_pedido'] is False


def test_embudo_sin_visitas_no_inventa_datos():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'Embudo vacio', 'bi04_embudo_vacio')
    with app.app_context():
        resultado = embudo_platos(cliente_id, _periodo())
    assert resultado == {
        'hay_visitas': False, 'visitas': 0, 'visitantes': 0, 'pedidos_web': 0, 'platos': [], 'atencion': [],
    }


def test_visita_al_detalle_publico_de_un_plato_se_registra_sin_guardar_la_ip():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'Embudo tienda', 'bi04_embudo_tienda')
    plato = _producto(app, cliente_id, 'Plato publico')
    with app.app_context():
        db.session.add(TiendaConfig(id_cliente=cliente_id, slug='pizzeria-embudo', nombre_tienda='Pizzeria', activa=True))
        db.session.commit()
    anonimo = app.test_client()

    primera = anonimo.get(f'/api/tienda/pizzeria-embudo/producto/{plato}', headers={'User-Agent': 'Navegador A'})
    segunda = anonimo.get(f'/api/tienda/pizzeria-embudo/producto/{plato}', headers={'User-Agent': 'Navegador B'})
    inexistente = anonimo.get('/api/tienda/pizzeria-embudo/producto/999999', headers={'User-Agent': 'Navegador A'})

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert inexistente.status_code == 404
    with app.app_context():
        visitas = GastronomiaTiendaVisita.query.filter_by(cliente_id=cliente_id, producto_id=plato).all()
        assert len(visitas) == 2
        assert len({visita.visitante_hash for visita in visitas}) == 2
        assert all(len(visita.visitante_hash) == 64 for visita in visitas)


def test_resumen_embudo_se_degrada_sin_romper_el_panel(monkeypatch):
    def _falla(*args, **kwargs):
        raise RuntimeError('fallo simulado')

    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'Embudo degradado', 'bi04_embudo_degradado')
    monkeypatch.setattr('gastronomia.services.bi.embudo.embudo_platos', _falla)
    with app.app_context():
        assert resumen_embudo_seguro(cliente_id) == {'disponible': False}


def test_tab_muestra_el_embudo_con_atencion_y_estado_vacio():
    app = create_app('testing')
    client = app.test_client()
    _negocio_con_embudo(app, 'bi04_embudo_tab')
    _loguear(client, app, 'bi04_embudo_tab')

    html = client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)

    assert 'Tienda online: de la visita al pedido' in html
    assert 'Miran pero no piden' in html
    assert 'Plato A: 6 visitantes' in html
    assert 'no guardamos la IP' in html

    vacio = app.test_client()
    cliente_vacio, _, _ = _crear_negocio(app, 'Embudo sin visitas', 'bi04_embudo_sin_visitas')
    _loguear(vacio, app, 'bi04_embudo_sin_visitas')
    html_vacio = vacio.get('/inteligencia?vista=gastronomia').get_data(as_text=True)
    assert 'Todavía no hay visitas a platos de la tienda online' in html_vacio
