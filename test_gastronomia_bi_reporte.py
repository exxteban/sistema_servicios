"""BI-03: reporte de valor del mes, comision evitada y mensajes de vuelta (datos ficticios).

Las fechas son fijas (HOY y AHORA) para que el resultado no dependa del dia de ejecucion.
"""
import re
from datetime import date, datetime, timedelta

import pytest

from app import create_app, db
from app.models import Cliente, Usuario
from app.utils.helpers import today_local, utc_bounds_for_local_dates
from gastronomia.bi_models import GastronomiaBiContacto
from gastronomia.models import (
    GastronomiaCategoria,
    GastronomiaClienteConfig,
    GastronomiaPedido,
    GastronomiaPedidoItem,
    GastronomiaProducto,
)
from gastronomia.services.bi.comision import guardar_porcentajes, leer_porcentajes
from gastronomia.services.bi.reporte_valor import (
    periodos,
    resumen_reporte_valor,
    resumen_reporte_valor_seguro,
    variacion,
)

HOY = date(2026, 10, 20)
AHORA = datetime(2026, 10, 25, 12, 0)


def _loguear(client, app, username: str):
    with app.app_context():
        usuario = Usuario.query.filter_by(username=username).first()
        user_id = usuario.id_usuario
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def _csrf(html: str) -> str:
    match = re.search(r'id="csrf-token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _crear_negocio(app, username: str):
    with app.app_context():
        cliente = Cliente(nombre=f'Negocio {username}', ruc_ci=username, tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.flush()
        usuario = Usuario(
            id_cliente=cliente.id_cliente,
            username=username,
            nombre_completo=f'Admin {username}',
            id_rol=1,
            activo=True,
        )
        usuario.set_password('clave123')
        categoria = GastronomiaCategoria(cliente_id=cliente.id_cliente, nombre='Reporte BI')
        db.session.add_all([
            usuario,
            categoria,
            GastronomiaClienteConfig(cliente_id=cliente.id_cliente, modo_operacion='gastronomia', gastronomia_activo=True),
        ])
        db.session.flush()
        producto = GastronomiaProducto(
            cliente_id=cliente.id_cliente,
            categoria_id=categoria.id_categoria,
            nombre='Milanesa BI',
            precio=30000,
            disponible=True,
            visible=True,
            activo=True,
        )
        db.session.add(producto)
        db.session.commit()
        return cliente.id_cliente, usuario.id_usuario, producto.id_producto


def _pedido_el(app, cliente_id, usuario_id, producto_id, dia: date, *, total: float, celular: str | None = None,
               nombre: str = 'Cliente', origen: str = 'pos', canal_precio: str | None = None,
               estado: str = 'cobrado') -> int:
    inicio_utc, _ = utc_bounds_for_local_dates(dia, dia)
    with app.app_context():
        pedido = GastronomiaPedido(
            cliente_id=cliente_id,
            usuario_id=usuario_id,
            tipo_pedido='mostrador',
            origen_pedido=origen,
            estado=estado,
            nombre_cliente=nombre,
            celular_cliente=celular,
            fecha_creacion=inicio_utc + timedelta(hours=12),
            subtotal=total,
            total=total,
        )
        db.session.add(pedido)
        db.session.flush()
        db.session.add(GastronomiaPedidoItem(
            pedido_id=pedido.id_pedido,
            cliente_id=cliente_id,
            producto_id=producto_id,
            nombre_producto='Milanesa BI',
            cantidad=1,
            precio_unitario=total,
            precio_original=total,
            subtotal=total,
            canal_precio=canal_precio,
        ))
        db.session.commit()
        return pedido.id_pedido


def _reporte(app, cliente_id):
    with app.app_context():
        return resumen_reporte_valor(cliente_id, hoy=HOY, ahora=AHORA)


def test_periodos_comparan_mismos_dias_del_mes_anterior():
    actual, anterior = periodos(date(2026, 10, 20))
    assert actual == {'desde': date(2026, 10, 1), 'hasta': date(2026, 10, 20)}
    assert anterior == {'desde': date(2026, 9, 1), 'hasta': date(2026, 9, 20)}

    _, anterior_corto = periodos(date(2026, 3, 31))
    assert anterior_corto['hasta'] == date(2026, 2, 28)

    _, anterior_primer_dia = periodos(date(2026, 11, 1))
    assert anterior_primer_dia == {'desde': date(2026, 10, 1), 'hasta': date(2026, 10, 1)}


def test_variacion_sin_base_previa_no_se_muestra_como_cero():
    assert variacion(50000, 25000) == 100.0
    assert variacion(0, 20000) == -100.0
    assert variacion(10000, 0) is None


def test_reporte_separa_canal_propio_de_plataformas_y_compara_con_el_mes_anterior():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'bi03_canales')
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 10, 2), total=30000)
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 10, 5), total=20000,
               celular='0981 300 001', origen='tienda_online')
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 10, 7), total=25000, canal_precio='pedidosya')
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 10, 9), total=99000, estado='cancelado')
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 9, 5), total=10000)

    reporte = _reporte(app, cliente_id)

    assert reporte['pedidos']['pedidos'] == 3
    assert reporte['pedidos']['ventas'] == 75000.0
    assert reporte['pedidos']['propios']['pedidos'] == 2
    assert reporte['pedidos']['propios']['ventas'] == 50000.0
    assert reporte['pedidos']['plataformas']['ventas'] == 25000.0
    assert reporte['comparacion'] == {'pedidos': 200.0, 'ventas': 650.0, 'ventas_propias': 400.0}


def test_clientes_nuevos_cuentan_telefonos_y_nunca_nombres_repetidos():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'bi03_nuevos')
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 9, 10), total=30000, celular='0981 200 001')
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 10, 3), total=30000, celular='0981 200 001')
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 10, 8), total=30000, celular='0981 200 002')
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 10, 12), total=30000,
               celular='0981 200 003', nombre='Ana')
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 10, 15), total=30000,
               celular='0981 200 004', nombre='Ana')
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 10, 9), total=30000)

    reporte = _reporte(app, cliente_id)

    assert reporte['clientes_nuevos'] == 3


def test_mensajes_separan_volvieron_observacion_y_fuera_del_mes():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'bi03_mensajes')
    pedido_a = _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 10, 10), total=30000,
                          celular='0981 200 001')
    with app.app_context():
        db.session.add_all([
            # Segunda compra enviada el 3 de octubre: la ventana de 15 dias cerro el 18 y tuvo una compra.
            GastronomiaBiContacto(
                cliente_id=cliente_id, telefono_normalizado='+595981200001', nombre='Volvio',
                segmento='segunda_compra', ultimo_pedido_id=pedido_a, estado='enviado',
                fecha_estado=datetime(2026, 10, 3, 12),
            ),
            # Habitual ausente enviado el 5 de octubre: la ventana de 30 dias sigue abierta.
            GastronomiaBiContacto(
                cliente_id=cliente_id, telefono_normalizado='+595981200002', nombre='Abierto',
                segmento='habitual_ausente', ultimo_pedido_id=2, estado='enviado',
                fecha_estado=datetime(2026, 10, 5, 12),
            ),
            # Enviado el 1 de octubre sin compra posterior: cerrado y no volvio.
            GastronomiaBiContacto(
                cliente_id=cliente_id, telefono_normalizado='+595981200003', nombre='No volvio',
                segmento='segunda_compra', ultimo_pedido_id=3, estado='enviado',
                fecha_estado=datetime(2026, 10, 1, 12),
            ),
            # Enviado en septiembre: no es del mes.
            GastronomiaBiContacto(
                cliente_id=cliente_id, telefono_normalizado='+595981200004', nombre='Septiembre',
                segmento='segunda_compra', ultimo_pedido_id=4, estado='enviado',
                fecha_estado=datetime(2026, 9, 20, 12),
            ),
        ])
        db.session.commit()

    reporte = _reporte(app, cliente_id)

    assert reporte['mensajes'] == {
        'enviados': 3,
        'enviados_cerrados': 2,
        'volvieron': 1,
        'en_observacion': 1,
    }


def test_comision_evitada_solo_se_estima_con_porcentaje_configurado():
    app = create_app('testing')
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'bi03_comision')
    _pedido_el(app, cliente_id, usuario_id, producto_id, date(2026, 10, 7), total=25000, canal_precio='pedidosya')
    assert _reporte(app, cliente_id)['comision'] is None

    with app.app_context():
        guardar_porcentajes(cliente_id, {'comision_pedidosya': '25', 'comision_monchis': ' '})
        assert leer_porcentajes(cliente_id) == {'pedidosya': 25.0, 'monchis': None}
    assert _reporte(app, cliente_id)['comision']['monto'] == 6250.0

    with app.app_context():
        guardar_porcentajes(cliente_id, {'comision_pedidosya': '12,5'})
        assert leer_porcentajes(cliente_id)['pedidosya'] == 12.5
    assert _reporte(app, cliente_id)['comision']['monto'] == 3125.0


def test_comision_rechaza_valores_invalidos_sin_cambiar_lo_guardado():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'bi03_validacion')
    with app.app_context():
        guardar_porcentajes(cliente_id, {'comision_pedidosya': '20'})
        for datos in ({'comision_pedidosya': '150'}, {'comision_pedidosya': 'abc'},
                      {'comision_pedidosya': '20', 'comision_monchis': '-1'}):
            with pytest.raises(ValueError):
                guardar_porcentajes(cliente_id, datos)
        assert leer_porcentajes(cliente_id) == {'pedidosya': 20.0, 'monchis': None}


def test_sin_pedidos_el_reporte_no_inventa_cifras():
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'bi03_vacio')

    reporte = _reporte(app, cliente_id)

    assert reporte['pedidos']['pedidos'] == 0
    assert reporte['comparacion'] == {'pedidos': None, 'ventas': None, 'ventas_propias': None}
    assert reporte['identidad']['porcentaje'] is None
    assert reporte['clientes_nuevos'] == 0
    assert reporte['comision'] is None
    assert reporte['acompanamientos'] is None


def test_bloque_reporte_de_valor_se_degrada_sin_romper_el_panel(monkeypatch):
    app = create_app('testing')
    cliente_id, _, _ = _crear_negocio(app, 'bi03_degradado')

    def _falla(*args, **kwargs):
        raise RuntimeError('fallo simulado')

    monkeypatch.setattr('gastronomia.services.bi.reporte_valor.resumen_reporte_valor', _falla)
    with app.app_context():
        assert resumen_reporte_valor_seguro(cliente_id) == {'disponible': False}


def test_tab_gastronomia_muestra_reporte_y_guarda_comision_por_post():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'bi03_panel')
    _pedido_el(app, cliente_id, usuario_id, producto_id, today_local(), total=30000)
    _loguear(client, app, 'bi03_panel')

    html = client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)
    assert 'Tu mes en el sistema' in html
    assert 'Mensajes de vuelta' in html
    assert 'Todavía no marcaste mensajes enviados' in html
    assert 'Configurar comisiones de plataformas' in html
    assert '1 pedido' in html
    assert '₲ 30.000' in html

    csrf = _csrf(client.get('/gastronomia/menu').get_data(as_text=True))
    respuesta = client.post(
        '/gastronomia/bi/comision',
        data={'comision_pedidosya': '30', 'csrf_token': csrf},
        headers={'X-CSRFToken': csrf},
    )
    assert respuesta.status_code == 302
    assert '/inteligencia' in respuesta.headers['Location']
    with app.app_context():
        assert leer_porcentajes(cliente_id)['pedidosya'] == 30.0

    respuesta_invalida = client.post(
        '/gastronomia/bi/comision',
        data={'comision_pedidosya': '300', 'csrf_token': csrf},
        headers={'X-CSRFToken': csrf},
    )
    assert respuesta_invalida.status_code == 302
    with app.app_context():
        assert leer_porcentajes(cliente_id)['pedidosya'] == 30.0


def test_tab_muestra_comision_y_mensajes_cuando_hay_datos():
    app = create_app('testing')
    client = app.test_client()
    cliente_id, usuario_id, producto_id = _crear_negocio(app, 'bi03_render')
    hoy = today_local()
    _pedido_el(app, cliente_id, usuario_id, producto_id, hoy, total=25000, canal_precio='pedidosya')
    with app.app_context():
        guardar_porcentajes(cliente_id, {'comision_pedidosya': '25'})
        db.session.add(GastronomiaBiContacto(
            cliente_id=cliente_id, telefono_normalizado='+595981200009', nombre='Enviado',
            segmento='segunda_compra', ultimo_pedido_id=1, estado='enviado', fecha_estado=datetime.utcnow(),
        ))
        db.session.commit()
    _loguear(client, app, 'bi03_render')

    html = client.get('/inteligencia?vista=gastronomia').get_data(as_text=True)

    assert 'Comisión evitada estimada: ₲ 6.250' in html
    assert 'Enviados: 1.' in html
    assert 'PedidosYa: ₲ 25.000 en ventas × 25.0%' in html
