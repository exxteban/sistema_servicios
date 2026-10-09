"""Los pagos de pedidos entran en Contabilidad como cobro, por metodo.

La entrega del pedido genera la venta sin pagos: la plata entro antes, como
sena o pago del pedido. Antes el efectivo caia en "Ingresos Manuales /
Ajustes" y una transferencia no aparecia en ningun lado del informe.
"""
from app import create_app, db
from app.models import Cliente, MetodoPago, PedidoCliente, PedidoClienteDetalle
from app.routes.caja.contabilidad_report import calcular_informe_contable_rango
from app.utils.helpers import today_local, utc_bounds_for_local_dates
from pedidos.services.pago_service import registrar_pago_pedido
from pedidos.services.pedido_service import recalcular_totales_pedido

from test_ventas_credito_modal_ui import _abrir_caja, _crear_producto, _loguear_admin, _obtener_metodo_efectivo


def _pedido(cliente, admin, producto, precio):
    pedido = PedidoCliente(
        id_cliente=int(cliente.id_cliente),
        id_usuario_creacion=int(admin.id_usuario),
        id_usuario_modificacion=int(admin.id_usuario),
        estado='pendiente_sena',
    )
    db.session.add(pedido)
    db.session.flush()
    db.session.add(PedidoClienteDetalle(
        id_pedido=int(pedido.id_pedido), id_producto=int(producto.id_producto), cantidad=1,
        precio_unitario=precio, porcentaje_iva=10, subtotal=precio,
        producto_codigo_snapshot=producto.codigo, producto_nombre_snapshot=producto.nombre,
    ))
    db.session.flush()
    recalcular_totales_pedido(pedido)
    return pedido


def test_pagos_de_pedido_cuentan_como_cobro_por_metodo():
    app = create_app('testing')
    with app.app_context():
        client = app.test_client()
        admin = _loguear_admin(client)
        sesion = _abrir_caja(admin)
        cliente = Cliente(nombre='Cliente Pedido Contab', ruc_ci='8100100-1', tipo='minorista', activo=True)
        db.session.add(cliente)
        db.session.commit()
        efectivo = _obtener_metodo_efectivo()
        transferencia = MetodoPago.query.filter(MetodoPago.nombre.ilike('%transfer%')).first()
        assert efectivo is not None and transferencia is not None

        pedido = _pedido(cliente, admin, _crear_producto(100000, codigo='PED-CONTAB-1'), 100000)
        registrar_pago_pedido(pedido, id_metodo_pago=int(efectivo.id_metodo_pago), monto=30000,
                              tipo_pago='sena', id_usuario=int(admin.id_usuario), sesion=sesion)
        registrar_pago_pedido(pedido, id_metodo_pago=int(transferencia.id_metodo_pago), monto=70000,
                              tipo_pago='pago_total', id_usuario=int(admin.id_usuario), sesion=sesion,
                              referencia='TRX-1')
        db.session.commit()

        informe = calcular_informe_contable_rango(*utc_bounds_for_local_dates(today_local(), today_local()))
        conceptos = {c['concepto']: c['entrada'] for c in informe['conceptos']}
        assert conceptos.get(f'Cobrado en Pedidos - {efectivo.nombre}') == 30000
        assert conceptos.get(f'Cobrado en Pedidos - {transferencia.nombre}') == 70000
        assert 'Ingresos Manuales / Ajustes' not in conceptos
        assert informe['total_cobros_pedidos'] == 100000
        assert informe['resultado_caja_mes'] == 100000
        cobros = [d for d in informe['detalles'] if d['concepto'] == 'Cobro de Pedido']
        assert sorted(d['entrada'] for d in cobros) == [30000, 70000]


def test_pantalla_contabilidad_con_pestanas_y_pedidos():
    app = create_app('testing')
    with app.app_context():
        client = app.test_client()
        _loguear_admin(client)
        html = client.get('/caja/contabilidad').get_data(as_text=True)
        assert 'role="tablist"' in html
        for panel in ('contabilidad-panel-resumen', 'contabilidad-panel-flujo', 'contabilidad-panel-detalle'):
            assert f'id="{panel}"' in html
        assert 'Cómo se forma el movimiento neto' in html
        assert 'Cobrado en Pedidos' in html
        assert 'agruparDetalle(' in html
