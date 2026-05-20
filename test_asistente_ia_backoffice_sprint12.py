from datetime import datetime
from uuid import uuid4

from app import create_app, db
from app.models import (
    AgendaActividad,
    Caja,
    Categoria,
    Cliente,
    Compra,
    DetalleCompra,
    DetalleDevolucion,
    Devolucion,
    PresupuestoEmpresarial,
    Producto,
    Proveedor,
    RecepcionCompraUsado,
    SesionCaja,
    Usuario,
    VendedorUsado,
    Venta,
)
from app.services.ia_backoffice.tool_handlers import ejecutar_tool_backoffice
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS


def test_sprint12_catalogo_expone_nuevas_tools_operativas():
    nombres = {item['function']['name'] for item in BACKOFFICE_TOOLS}

    assert {
        'compras_resumen_periodo',
        'proveedores_top',
        'proveedor_detalle_360',
        'devoluciones_resumen',
        'productos_mas_devueltos',
        'motivos_de_devolucion',
        'usados_resumen',
        'usados_pendientes_revision',
        'usados_margen_estimado',
        'usados_por_estado',
        'presupuestos_resumen',
        'presupuestos_pendientes',
        'presupuestos_conversion',
        'presupuesto_detalle',
        'turnos_resumen',
        'turnos_proximos',
        'turnos_cancelados',
        'atenciones_resumen',
        'buscar_entidad_backoffice',
        'dashboard_operativo_hoy',
    }.issubset(nombres)


def test_sprint12_tools_compras_proveedores_devoluciones_usados_y_presupuestos():
    app = create_app('testing')

    with app.app_context():
        suffix = uuid4().hex[:8]
        admin = Usuario.query.filter_by(username='admin').first()
        caja = Caja.query.first()
        sesion = SesionCaja(id_caja=caja.id_caja, id_usuario=admin.id_usuario, estado='cerrada')
        cliente = Cliente(nombre=f'Cliente Sprint12 {suffix}', tipo='minorista', activo=True)
        proveedor = Proveedor(nombre=f'Proveedor Sprint12 {suffix}', ruc=f'RUC-{suffix}', activo=True)
        categoria = Categoria(nombre=f'Categoria Sprint12 {suffix}', activo=True)
        db.session.add_all([sesion, cliente, proveedor, categoria])
        db.session.flush()

        producto = Producto(
            codigo=f'P12-{suffix}',
            nombre=f'Producto Sprint12 {suffix}',
            id_categoria=categoria.id_categoria,
            id_proveedor_principal=proveedor.id_proveedor,
            precio_compra=1000,
            precio_venta=2500,
            stock_actual=3,
            stock_minimo=5,
        )
        db.session.add(producto)
        db.session.flush()

        compra = Compra(
            numero_factura=f'FAC-{suffix}',
            id_proveedor=proveedor.id_proveedor,
            id_usuario=admin.id_usuario,
            fecha_compra=datetime(2026, 4, 10).date(),
            subtotal=1000,
            total=1000,
            estado='completada',
            pagada=True,
        )
        db.session.add(compra)
        db.session.flush()
        db.session.add(DetalleCompra(
            id_compra=compra.id_compra,
            id_producto=producto.id_producto,
            cantidad=2,
            precio_unitario=500,
            subtotal=1000,
        ))

        venta = Venta(
            id_cliente=cliente.id_cliente,
            id_sesion_caja=sesion.id_sesion,
            fecha_venta=datetime(2026, 4, 11, 10, 0, 0),
            subtotal=2500,
            total=2500,
            estado='completada',
        )
        db.session.add(venta)
        db.session.flush()
        devolucion = Devolucion(
            id_venta=venta.id_venta,
            id_usuario=admin.id_usuario,
            id_sesion_caja=sesion.id_sesion,
            fecha_devolucion=datetime(2026, 4, 12, 10, 0, 0),
            motivo='Cambio por falla',
            accion_stock='retorno_stock',
            monto_total=2500,
        )
        db.session.add(devolucion)
        db.session.flush()
        db.session.add(DetalleDevolucion(
            id_devolucion=devolucion.id_devolucion,
            id_producto=producto.id_producto,
            cantidad=1,
            precio_unitario=2500,
            subtotal=2500,
        ))

        vendedor = VendedorUsado(
            nombres_apellidos=f'Vendedor Usado {suffix}',
            tipo_documento='CI',
            numero_documento=f'DOC-{suffix}',
            numero_documento_normalizado=f'DOC-{suffix}',
        )
        db.session.add(vendedor)
        db.session.flush()
        db.session.add(RecepcionCompraUsado(
            fecha_formulario=datetime(2026, 4, 13).date(),
            id_vendedor_usado=vendedor.id_vendedor_usado,
            id_usuario=admin.id_usuario,
            id_producto=producto.id_producto,
            id_compra=compra.id_compra,
            descripcion_producto='Celular usado',
            vendedor_nombres_apellidos=vendedor.nombres_apellidos,
            vendedor_tipo_documento='CI',
            vendedor_numero_documento=vendedor.numero_documento,
            monto_compra=1000,
            metodo_pago='efectivo',
        ))

        presupuesto = PresupuestoEmpresarial(
            numero_presupuesto=900000 + int(suffix[:4], 16) % 9999,
            fecha_emision=datetime(2026, 4, 14).date(),
            id_usuario=admin.id_usuario,
            id_cliente=cliente.id_cliente,
            destinatario_nombre=f'Empresa Sprint12 {suffix}',
            asunto='Equipos corporativos',
            subtotal=5000,
            total=5000,
            items_json='[{"descripcion":"Equipo","cantidad":2}]',
        )
        db.session.add(presupuesto)

        db.session.add(AgendaActividad(
            tipo='turno',
            titulo=f'Turno Sprint12 {suffix}',
            fecha_inicio=datetime(2026, 4, 15, 9, 0, 0),
            estado='pendiente',
            prioridad='media',
            usuario_id=admin.id_usuario,
            creado_por_id=admin.id_usuario,
            cliente_id=cliente.id_cliente,
            origen_modulo='atenciones',
        ))
        db.session.commit()

        args = {'periodo': 'custom', 'desde': '2026-04-01', 'hasta': '2026-04-30', 'top_n': 5}
        assert ejecutar_tool_backoffice('compras_resumen_periodo', args, usuario=admin)['data']['total_compras'] >= 1000
        assert ejecutar_tool_backoffice('proveedores_top', args, usuario=admin)['data']['proveedores'][0]['id_proveedor'] == proveedor.id_proveedor
        assert ejecutar_tool_backoffice('proveedor_detalle_360', {'id_proveedor': proveedor.id_proveedor}, usuario=admin)['data']['encontrado'] is True
        assert ejecutar_tool_backoffice('devoluciones_resumen', args, usuario=admin)['data']['cantidad_devoluciones'] >= 1
        assert ejecutar_tool_backoffice('productos_mas_devueltos', args, usuario=admin)['data']['productos'][0]['codigo'] == producto.codigo
        assert ejecutar_tool_backoffice('motivos_de_devolucion', args, usuario=admin)['data']['motivos'][0]['motivo'] == 'Cambio por falla'
        assert ejecutar_tool_backoffice('usados_resumen', args, usuario=admin)['data']['cantidad_recepciones'] >= 1
        assert ejecutar_tool_backoffice('usados_margen_estimado', args, usuario=admin)['data']['margen_estimado_total'] >= 1500
        assert ejecutar_tool_backoffice('presupuestos_resumen', args, usuario=admin)['data']['cantidad_presupuestos'] >= 1
        assert ejecutar_tool_backoffice('presupuesto_detalle', {'referencia': f'Empresa Sprint12 {suffix}'}, usuario=admin)['data']['encontrado'] is True
        assert ejecutar_tool_backoffice('turnos_resumen', args, usuario=admin)['data']['cantidad_actividades'] >= 1
        assert ejecutar_tool_backoffice('atenciones_resumen', args, usuario=admin)['data']['cantidad_atenciones_agendadas'] >= 1
        busqueda = ejecutar_tool_backoffice('buscar_entidad_backoffice', {'busqueda': suffix}, usuario=admin)
        assert busqueda['ok'] is True
        assert busqueda['data']['total_resultados'] >= 1
        dashboard = ejecutar_tool_backoffice('dashboard_operativo_hoy', {}, usuario=admin)
        assert dashboard['ok'] is True
        assert 'ventas' in dashboard['data']
