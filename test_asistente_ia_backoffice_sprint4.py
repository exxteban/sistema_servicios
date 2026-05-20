from datetime import date, datetime
from uuid import uuid4

from app import create_app, db
from app.models import (
    Auditoria,
    Caja,
    Categoria,
    Cliente,
    GastoCorriente,
    MetodoPago,
    MovimientoCaja,
    PagoGastoCorriente,
    PagoVenta,
    Producto,
    Rol,
    SesionCaja,
    Usuario,
    Venta,
)
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS


def test_sprint4_catalogo_habilita_tools_de_gastos_y_caja():
    nombres = {item['function']['name'] for item in BACKOFFICE_TOOLS}
    assert {
        'gastos_resumen_periodo',
        'gastos_por_categoria',
        'gastos_vencidos',
        'caja_resumen_periodo',
        'caja_estado_actual',
        'caja_anulaciones_periodo',
    }.issubset(nombres)


def test_tools_gastos_corrientes_devuelven_resumen_categorias_y_vencidos():
    app = create_app('testing')

    with app.app_context():
        suffix = uuid4().hex[:8]
        admin = Usuario.query.filter_by(username='admin').first()
        alquiler = GastoCorriente(
            nombre=f'Alquiler IA {suffix}',
            categoria='local',
            monto_estimado=3000,
            dia_vencimiento=1,
            activo=True,
            alerta_activa=True,
            fecha_creacion=datetime(2026, 3, 1, 10, 0, 0),
        )
        internet = GastoCorriente(
            nombre=f'Internet IA {suffix}',
            categoria='servicios',
            monto_estimado=2000,
            dia_vencimiento=28,
            activo=True,
            alerta_activa=True,
            fecha_creacion=datetime(2026, 3, 1, 10, 0, 0),
        )
        db.session.add_all([alquiler, internet])
        db.session.flush()
        db.session.add(PagoGastoCorriente(
            id_gasto_corriente=internet.id_gasto_corriente,
            periodo_anio=2026,
            periodo_mes=4,
            fecha_vencimiento=date(2026, 4, 28),
            fecha_pago=date(2026, 4, 10),
            monto_estimado=2000,
            monto_pagado=2000,
            estado='pagado',
        ))
        db.session.commit()

        args = {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 5}
        resumen = ejecutar_tool_backoffice('gastos_resumen_periodo', args, usuario=admin)
        assert resumen['ok'] is True
        assert resumen['data']['total_estimado'] == 5000
        assert resumen['data']['total_pagado'] == 2000
        assert resumen['data']['total_pendiente'] == 3000
        assert resumen['data']['vencidos'] >= 1

        categorias = ejecutar_tool_backoffice('gastos_por_categoria', args, usuario=admin)
        assert categorias['ok'] is True
        assert any(item['categoria'] == 'local' for item in categorias['data']['categorias'])

        vencidos = ejecutar_tool_backoffice('gastos_vencidos', args, usuario=admin)
        assert vencidos['ok'] is True
        assert any(item['nombre'] == f'Alquiler IA {suffix}' for item in vencidos['data']['gastos'])


def test_tools_caja_resumen_estado_y_anulaciones():
    app = create_app('testing')

    with app.app_context():
        suffix = uuid4().hex[:8]
        admin = Usuario.query.filter_by(username='admin').first()
        caja = Caja.query.first()
        metodo = MetodoPago.query.filter_by(nombre='Efectivo').first() or MetodoPago(nombre='Efectivo', activo=True)
        cliente = Cliente(nombre=f'Cliente Caja IA {suffix}', tipo='minorista', activo=True)
        categoria = Categoria(nombre=f'IA Caja Categoria {suffix}', activo=True)
        db.session.add_all([metodo, cliente, categoria])
        db.session.flush()
        producto = Producto(
            codigo=f'IA-CAJA-{suffix}',
            nombre=f'Producto Caja {suffix}',
            id_categoria=categoria.id_categoria,
            precio_compra=1000,
            precio_venta=3000,
            stock_actual=10,
        )
        db.session.add(producto)
        db.session.flush()

        sesion = SesionCaja(
            id_caja=caja.id_caja,
            id_usuario=admin.id_usuario,
            estado='abierta',
            monto_inicial=1000,
            fecha_apertura=datetime(2026, 4, 5, 8, 0, 0),
        )
        db.session.add(sesion)
        db.session.flush()
        venta = Venta(
            id_cliente=cliente.id_cliente,
            id_sesion_caja=sesion.id_sesion,
            id_usuario_vendedor=admin.id_usuario,
            fecha_venta=datetime(2026, 4, 5, 10, 0, 0),
            subtotal=3000,
            total=3000,
            estado='completada',
        )
        venta_anulada = Venta(
            id_cliente=cliente.id_cliente,
            id_sesion_caja=sesion.id_sesion,
            id_usuario_vendedor=admin.id_usuario,
            fecha_venta=datetime(2026, 4, 6, 10, 0, 0),
            subtotal=1500,
            total=1500,
            estado='anulada',
        )
        db.session.add_all([venta, venta_anulada])
        db.session.flush()
        db.session.add(PagoVenta(id_venta=venta.id_venta, id_metodo_pago=metodo.id_metodo_pago, monto=3000))
        db.session.add(MovimientoCaja(
            id_sesion_caja=sesion.id_sesion,
            id_usuario=admin.id_usuario,
            tipo='ingreso',
            monto=500,
            motivo='Ingreso manual IA',
            fecha_movimiento=datetime(2026, 4, 5, 11, 0, 0),
        ))
        db.session.add(MovimientoCaja(
            id_sesion_caja=sesion.id_sesion,
            id_usuario=admin.id_usuario,
            tipo='egreso',
            monto=1500,
            motivo='Anulacion venta IA',
            referencia_tipo='anulacion_venta',
            referencia_id=venta_anulada.id_venta,
            fecha_movimiento=datetime(2026, 4, 6, 11, 0, 0),
        ))
        db.session.add(Auditoria(
            id_usuario=admin.id_usuario,
            accion='anular_venta',
            modulo='ventas',
            descripcion='Anulacion IA de prueba',
            referencia_tipo='venta',
            referencia_id=venta_anulada.id_venta,
            fecha_accion=datetime(2026, 4, 6, 11, 0, 0),
        ))
        db.session.commit()

        args = {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 5}
        resumen = ejecutar_tool_backoffice('caja_resumen_periodo', args, usuario=admin)
        assert resumen['ok'] is True
        assert resumen['data']['ventas_total'] >= 3000
        assert resumen['data']['ingresos_movimientos'] >= 500
        assert resumen['data']['egresos_movimientos'] >= 1500
        assert resumen['data']['metodos_pago'][0]['nombre'] == 'Efectivo'

        estado = ejecutar_tool_backoffice('caja_estado_actual', {'top_n': 10}, usuario=admin)
        assert estado['ok'] is True
        assert any(item['id_sesion'] == sesion.id_sesion for item in estado['data']['sesiones'])

        anulaciones = ejecutar_tool_backoffice('caja_anulaciones_periodo', args, usuario=admin)
        assert anulaciones['ok'] is True
        assert anulaciones['data']['cantidad_anulaciones'] >= 1
        assert anulaciones['data']['monto_egresos_anulacion'] >= 1500


def test_tools_sprint4_respetan_permisos_por_modulo():
    app = create_app('testing')

    with app.app_context():
        rol = Rol.query.filter_by(nombre='Tecnico').first()
        usuario = Usuario(
            username=f'sin_sprint4_ia_{uuid4().hex[:6]}',
            nombre_completo='Sin Sprint 4 IA',
            id_rol=rol.id_rol,
            activo=True,
        )
        usuario.set_password('1234')
        db.session.add(usuario)
        db.session.commit()

        assert ejecutar_tool_backoffice('gastos_resumen_periodo', {}, usuario=usuario)['error'] == 'sin_permiso_gastos'
        assert ejecutar_tool_backoffice('caja_resumen_periodo', {}, usuario=usuario)['error'] == 'sin_permiso_caja'
