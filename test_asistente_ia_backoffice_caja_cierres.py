from datetime import datetime, timedelta
from uuid import uuid4

from app import create_app, db
from app.models import (
    Auditoria,
    Caja,
    Categoria,
    Cliente,
    DetalleVenta,
    MetodoPago,
    MovimientoCaja,
    PagoVenta,
    Producto,
    SesionCaja,
    Usuario,
    Venta,
)
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS


def _metodo_efectivo():
    metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%efectivo%')).first()
    if metodo:
        return metodo
    metodo = MetodoPago(nombre='Efectivo', activo=True, orden_display=1)
    db.session.add(metodo)
    db.session.flush()
    return metodo


def _crear_venta(cliente, sesion, usuario, producto, metodo, fecha, total, estado='completada'):
    venta = Venta(
        id_cliente=cliente.id_cliente,
        id_sesion_caja=sesion.id_sesion,
        id_usuario_vendedor=usuario.id_usuario,
        fecha_venta=fecha,
        subtotal=total,
        total=total,
        estado=estado,
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
    db.session.add(PagoVenta(
        id_venta=venta.id_venta,
        id_metodo_pago=metodo.id_metodo_pago,
        monto=total,
        fecha_pago=fecha,
    ))
    return venta


def _crear_cierre_con_datos():
    suffix = uuid4().hex[:8]
    admin = Usuario.query.filter_by(username='admin').first()
    caja = Caja.query.first()
    cliente = Cliente(nombre=f'Cliente Cierre IA {suffix}', tipo='minorista', activo=True)
    categoria = Categoria(nombre=f'IA Cierre Categoria {suffix}', activo=True)
    db.session.add_all([cliente, categoria])
    db.session.flush()
    producto = Producto(
        codigo=f'IA-CIERRE-{suffix}',
        nombre=f'Producto Cierre {suffix}',
        id_categoria=categoria.id_categoria,
        precio_compra=5000,
        precio_venta=20000,
        stock_actual=10,
    )
    db.session.add(producto)
    db.session.flush()

    apertura = datetime(2026, 4, 12, 8, 0, 0)
    cierre = datetime(2026, 4, 12, 18, 0, 0)
    sesion = SesionCaja(
        id_caja=caja.id_caja,
        id_usuario=admin.id_usuario,
        id_usuario_cierre=admin.id_usuario,
        fecha_apertura=apertura,
        fecha_cierre=cierre,
        monto_inicial=100000,
        monto_final_sistema=115000,
        monto_final_declarado=114000,
        diferencia=-1000,
        estado='cerrada',
    )
    db.session.add(sesion)
    db.session.flush()

    metodo = _metodo_efectivo()
    _crear_venta(cliente, sesion, admin, producto, metodo, apertura + timedelta(hours=1), 20000)
    venta_anulada = _crear_venta(
        cliente,
        sesion,
        admin,
        producto,
        metodo,
        apertura + timedelta(hours=2),
        7000,
        estado='anulada',
    )
    db.session.add(MovimientoCaja(
        id_sesion_caja=sesion.id_sesion,
        id_usuario=admin.id_usuario,
        tipo='ingreso',
        monto=5000,
        motivo='Ajuste manual IA',
        fecha_movimiento=apertura + timedelta(hours=3),
    ))
    db.session.add(Auditoria(
        id_usuario=admin.id_usuario,
        accion='anular_venta',
        modulo='ventas',
        descripcion='Anulacion de venta para cierre IA',
        referencia_tipo='venta',
        referencia_id=venta_anulada.id_venta,
        fecha_accion=apertura + timedelta(hours=4),
    ))
    db.session.commit()
    return admin, sesion.id_sesion


def test_catalogo_habilita_tools_de_cierres_de_caja():
    nombres = {item['function']['name'] for item in BACKOFFICE_TOOLS}
    assert {
        'caja_cierres_recientes',
        'caja_cierre_detalle',
        'caja_cierre_diferencia',
        'caja_cierre_metodos_pago',
        'caja_cierre_movimientos',
        'caja_cierre_anulaciones',
    }.issubset(nombres)


def test_tools_cierres_explican_diferencia_metodos_movimientos_y_anulaciones():
    app = create_app('testing')

    with app.app_context():
        admin, sesion_id = _crear_cierre_con_datos()
        args = {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 10}

        recientes = ejecutar_tool_backoffice('caja_cierres_recientes', args, usuario=admin)
        assert recientes['ok'] is True
        assert any(item['id_sesion'] == sesion_id for item in recientes['data']['cierres'])

        detalle = ejecutar_tool_backoffice('caja_cierre_detalle', {'id_sesion': sesion_id}, usuario=admin)
        assert detalle['ok'] is True
        assert detalle['data']['encontrado'] is True
        assert detalle['data']['sesion']['diferencia'] == -1000
        assert any(item['key'] == 'ventas_metodo' for item in detalle['data']['conceptos'])

        diferencia = ejecutar_tool_backoffice('caja_cierre_diferencia', {'id_sesion': sesion_id}, usuario=admin)
        assert diferencia['ok'] is True
        assert diferencia['data']['estado_diferencia'] == 'faltante'
        assert diferencia['data']['monto_declarado'] == 114000
        assert diferencia['data']['monto_sistema'] == 115000

        metodos = ejecutar_tool_backoffice('caja_cierre_metodos_pago', {'id_sesion': sesion_id}, usuario=admin)
        assert metodos['ok'] is True
        assert any(item['total'] == 20000 for item in metodos['data']['ventas_por_metodo'])

        movimientos = ejecutar_tool_backoffice('caja_cierre_movimientos', {'id_sesion': sesion_id}, usuario=admin)
        assert movimientos['ok'] is True
        assert any(item['referencia'] == 'Ajuste manual IA' for item in movimientos['data']['movimientos'])

        anulaciones = ejecutar_tool_backoffice('caja_cierre_anulaciones', {'id_sesion': sesion_id}, usuario=admin)
        assert anulaciones['ok'] is True
        assert anulaciones['data']['cantidad_anulaciones'] == 1
        assert anulaciones['data']['total_anulado'] == 7000
