from datetime import datetime
from uuid import uuid4

from app import create_app, db
from app.models import Caja, Categoria, Cliente, DetalleVenta, Producto, SesionCaja, Usuario, Venta
from app.services.ia_backoffice.response_engine import _guia_tools_prioritarias, _respuesta_directa_tool
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice


def test_sprint11_guia_prioriza_ranking_mensual_para_consulta_por_mes():
    guia = _guia_tools_prioritarias([
        {'role': 'user', 'content': 'Que mes se vendio mas hasta ahora? Mostrame el detalle por mes.'},
    ])

    assert 'ventas_ranking_mensual' in guia


def test_sprint11_ranking_mensual_y_respuesta_directa_salen_del_mismo_dato():
    app = create_app('testing')

    with app.app_context():
        suffix = uuid4().hex[:8]
        admin = Usuario.query.filter_by(username='admin').first()
        caja = Caja.query.first()
        cliente = Cliente(nombre=f'Cliente Ranking {suffix}', tipo='minorista', activo=True)
        categoria = Categoria(nombre=f'IA Ranking Categoria {suffix}', activo=True)
        db.session.add_all([cliente, categoria])
        db.session.flush()
        producto = Producto(
            codigo=f'IA-RANK-{suffix}',
            nombre=f'Producto Ranking {suffix}',
            id_categoria=categoria.id_categoria,
            precio_compra=1000,
            precio_venta=2000,
            stock_actual=10,
        )
        db.session.add(producto)
        db.session.flush()
        sesion = SesionCaja(id_caja=caja.id_caja, id_usuario=admin.id_usuario, estado='cerrada')
        db.session.add(sesion)
        db.session.flush()

        def crear_venta(fecha, total):
            venta = Venta(
                id_cliente=cliente.id_cliente,
                id_sesion_caja=sesion.id_sesion,
                fecha_venta=fecha,
                subtotal=total,
                total=total,
                estado='completada',
            )
            db.session.add(venta)
            db.session.flush()
            db.session.add(DetalleVenta(
                id_venta=venta.id_venta,
                id_producto=producto.id_producto,
                cantidad=1,
                precio_unitario=total,
                precio_original=total,
                porcentaje_iva=10,
                monto_iva=0,
                subtotal=total,
            ))

        crear_venta(datetime(2026, 1, 10, 10, 0, 0), 500000)
        crear_venta(datetime(2026, 3, 5, 11, 0, 0), 23056000)
        crear_venta(datetime(2026, 4, 8, 12, 0, 0), 21239529)
        db.session.commit()

        resultado = ejecutar_tool_backoffice(
            'ventas_ranking_mensual',
            {'periodo': 'custom', 'desde': '2026-01-01', 'hasta': '2026-04-30'},
            usuario=admin,
        )
        texto = _respuesta_directa_tool('ventas_ranking_mensual', resultado)

    assert resultado['ok'] is True
    assert resultado['data']['mejor_mes']['mes_nombre'] == 'Marzo'
    assert resultado['data']['mejor_mes']['total_ventas'] == 23056000
    assert resultado['data']['detalle_cronologico'][1]['mes_nombre'] == 'Febrero'
    assert resultado['data']['detalle_cronologico'][1]['total_ventas'] == 0
    assert resultado['data']['detalle_cronologico'][3]['mes_nombre'] == 'Abril'
    assert resultado['data']['detalle_cronologico'][3]['total_ventas'] == 21239529
    assert 'el mes con mas ventas fue marzo con Gs. 23.056.000.' in texto
    assert '- Febrero: Gs. 0 en 0 ventas' in texto
    assert '- Marzo: Gs. 23.056.000 en 1 ventas' in texto
    assert '- Abril: Gs. 21.239.529 en 1 ventas' in texto
