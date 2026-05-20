from datetime import datetime
from uuid import uuid4

from app import create_app, db
from app.models import Caja, Categoria, Cliente, DetalleVenta, Producto, SesionCaja, Usuario, Venta
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS


def _crear_venta(cliente, sesion, usuario, producto, fecha, total, cantidad=1, descuento=0):
    venta = Venta(
        id_cliente=cliente.id_cliente,
        id_sesion_caja=sesion.id_sesion,
        id_usuario_vendedor=usuario.id_usuario,
        fecha_venta=fecha,
        subtotal=total + descuento,
        descuento_monto=descuento,
        total=total,
        estado='completada',
    )
    db.session.add(venta)
    db.session.flush()
    db.session.add(DetalleVenta(
        id_venta=venta.id_venta,
        id_producto=producto.id_producto,
        cantidad=cantidad,
        precio_unitario=total / cantidad,
        precio_original=total / cantidad,
        porcentaje_iva=10,
        monto_iva=0,
        subtotal=total,
    ))
    return venta


def test_catalogo_habilita_tools_de_rentabilidad_ventas():
    nombres = {item['function']['name'] for item in BACKOFFICE_TOOLS}
    assert {
        'ventas_ganancia_periodo',
        'ventas_rentabilidad_productos',
        'ventas_productos_bajo_margen',
        'ventas_descuentos_periodo',
    }.issubset(nombres)


def test_tools_ventas_calculan_ganancia_margen_y_productos_rentables():
    app = create_app('testing')

    with app.app_context():
        suffix = uuid4().hex[:8]
        admin = Usuario.query.filter_by(username='admin').first()
        caja = Caja.query.first()
        cliente = Cliente(nombre=f'Cliente Rentabilidad IA {suffix}', tipo='minorista', activo=True)
        categoria = Categoria(nombre=f'IA Rentabilidad Categoria {suffix}', activo=True)
        db.session.add_all([cliente, categoria])
        db.session.flush()

        producto_margen_alto = Producto(
            codigo=f'IA-MARGEN-ALTO-{suffix}',
            nombre=f'Producto Margen Alto {suffix}',
            id_categoria=categoria.id_categoria,
            precio_compra=500,
            precio_venta=4000,
            stock_actual=10,
        )
        producto_margen_bajo = Producto(
            codigo=f'IA-MARGEN-BAJO-{suffix}',
            nombre=f'Producto Margen Bajo {suffix}',
            id_categoria=categoria.id_categoria,
            precio_compra=900,
            precio_venta=1000,
            stock_actual=10,
        )
        db.session.add_all([producto_margen_alto, producto_margen_bajo])
        db.session.flush()

        sesion = SesionCaja(id_caja=caja.id_caja, id_usuario=admin.id_usuario, estado='cerrada')
        db.session.add(sesion)
        db.session.flush()
        _crear_venta(cliente, sesion, admin, producto_margen_alto, datetime(2026, 4, 8, 10, 0, 0), 4000)
        _crear_venta(cliente, sesion, admin, producto_margen_bajo, datetime(2026, 4, 9, 10, 0, 0), 1000)
        db.session.commit()

        args = {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 5}
        ganancia = ejecutar_tool_backoffice('ventas_ganancia_periodo', args, usuario=admin)
        assert ganancia['ok'] is True
        assert ganancia['data']['total_ventas'] == 5000
        assert ganancia['data']['costo_estimado'] == 1400
        assert ganancia['data']['ganancia_bruta_estimada'] == 3600
        assert ganancia['data']['margen_bruto_pct'] == 72.0

        rentables = ejecutar_tool_backoffice('ventas_rentabilidad_productos', args, usuario=admin)
        assert rentables['ok'] is True
        assert rentables['data']['productos'][0]['codigo'] == f'IA-MARGEN-ALTO-{suffix}'
        assert rentables['data']['productos'][0]['ganancia_estimada'] == 3500

        bajo_margen = ejecutar_tool_backoffice('ventas_productos_bajo_margen', args, usuario=admin)
        assert bajo_margen['ok'] is True
        assert bajo_margen['data']['productos'][0]['codigo'] == f'IA-MARGEN-BAJO-{suffix}'
        assert bajo_margen['data']['productos'][0]['margen_pct'] == 10.0


def test_tool_ventas_descuentos_periodo_resume_descuentos_de_venta_y_linea():
    app = create_app('testing')

    with app.app_context():
        suffix = uuid4().hex[:8]
        admin = Usuario.query.filter_by(username='admin').first()
        caja = Caja.query.first()
        cliente = Cliente(nombre=f'Cliente Descuento IA {suffix}', tipo='minorista', activo=True)
        categoria = Categoria(nombre=f'IA Descuento Categoria {suffix}', activo=True)
        db.session.add_all([cliente, categoria])
        db.session.flush()
        producto = Producto(
            codigo=f'IA-DESC-{suffix}',
            nombre=f'Producto Descuento {suffix}',
            id_categoria=categoria.id_categoria,
            precio_compra=500,
            precio_venta=1000,
            stock_actual=10,
        )
        db.session.add(producto)
        db.session.flush()
        sesion = SesionCaja(id_caja=caja.id_caja, id_usuario=admin.id_usuario, estado='cerrada')
        db.session.add(sesion)
        db.session.flush()
        venta = _crear_venta(
            cliente,
            sesion,
            admin,
            producto,
            datetime(2026, 4, 10, 10, 0, 0),
            900,
            descuento=100,
        )
        db.session.flush()
        DetalleVenta.query.filter_by(id_venta=venta.id_venta).update({'descuento_linea': 50})
        db.session.commit()

        descuentos = ejecutar_tool_backoffice(
            'ventas_descuentos_periodo',
            {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30'},
            usuario=admin,
        )
        assert descuentos['ok'] is True
        assert descuentos['data']['descuento_ventas'] == 100
        assert descuentos['data']['descuento_lineas'] == 50
        assert descuentos['data']['descuento_total_estimado'] == 150
