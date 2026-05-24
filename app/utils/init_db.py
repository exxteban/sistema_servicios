"""
Utilidad para inicializar datos base del sistema
"""
import os
from app import db


def _require_safe_bootstrap_password(var_name: str, disallowed) -> str:
    value = os.environ.get(var_name)
    if value is None:
        raise RuntimeError(f'{var_name} debe estar configurado en producción')
    value = value.strip()
    if not value:
        raise RuntimeError(f'{var_name} debe estar configurado en producción')
    if value in disallowed:
        raise RuntimeError(f'{var_name} debe ser diferente al valor por defecto')
    if len(value) < 10:
        raise RuntimeError(f'{var_name} debe tener al menos 10 caracteres')
    return value


def inicializar_datos_base(config_name=None):
    """Inicializa los datos base si no existen"""
    from app.models import (
        Usuario, Caja, MetodoPago, Cliente, Categoria, Configuracion, Rol, Permiso
    )
    from app.services.ia_backoffice.settings import CLAVE_SYSTEM_ROOT_USER_ID
    from sqlalchemy import text
    from cobranzas import (
        CLAVE_COBRANZAS_ACTIVO,
        CLAVE_VENTAS_CREDITO_ACTIVO,
        CLAVE_VENTAS_CREDITO_METODO_PAGO_ID,
        DESC_COBRANZAS_ACTIVO,
        DESC_VENTAS_CREDITO_ACTIVO,
        DESC_VENTAS_CREDITO_METODO_PAGO_ID,
    )
    from flujo_caja import CLAVE_MODULO_FLUJO_CAJA, DESC_MODULO_FLUJO_CAJA

    is_production = (config_name or '').strip().lower() == 'production'
    
    if Rol.query.count() == 0:
        db.session.add_all([
            Rol(id_rol=1, nombre='Administrador', descripcion='Acceso total al sistema', nivel_jerarquia=100),
            Rol(id_rol=2, nombre='Supervisor', descripcion='Puede supervisar operaciones y generar reportes', nivel_jerarquia=50),
            Rol(id_rol=3, nombre='Cajero', descripcion='Operaciones básicas de venta y caja', nivel_jerarquia=10),
        ])
    if not Rol.query.filter_by(nombre='Root').first():
        db.session.add(Rol(nombre='Root', descripcion='Acceso total (superusuario)', nivel_jerarquia=1000))
    if not Rol.query.filter_by(nombre='Auditoria').first():
        db.session.add(Rol(nombre='Auditoria', descripcion='Puede consultar los logs de auditoría', nivel_jerarquia=90))
    if not Rol.query.filter_by(nombre='Vendedor').first():
        db.session.add(Rol(nombre='Vendedor', descripcion='Solo lectura y recepción', nivel_jerarquia=15))
    tecnico = Rol.query.filter_by(nombre='Tecnico').first()
    recepcion = Rol.query.filter_by(nombre='Recepcion').first()
    if recepcion and not tecnico:
        recepcion.nombre = 'Tecnico'
        recepcion.descripcion = 'Recepción de equipos para reparación'
        if recepcion.nivel_jerarquia is None:
            recepcion.nivel_jerarquia = 5
        if recepcion.activo is None:
            recepcion.activo = True
    elif recepcion and tecnico:
        recepcion.activo = False
        recepcion.descripcion = 'Rol obsoleto: usar Tecnico'
    elif not tecnico:
        db.session.add(Rol(nombre='Tecnico', descripcion='Recepción de equipos para reparación', nivel_jerarquia=5))
    if not Rol.query.filter_by(nombre='Cocina').first():
        db.session.add(Rol(nombre='Cocina', descripcion='Operacion de pantalla KDS gastronomica', nivel_jerarquia=12))
    if not Rol.query.filter_by(nombre='Mozo').first():
        db.session.add(Rol(nombre='Mozo', descripcion='Toma de pedidos y gestion de salon gastronomico', nivel_jerarquia=12))
    if not Rol.query.filter_by(nombre='Caja Gastronomia').first():
        db.session.add(Rol(nombre='Caja Gastronomia', descripcion='Cobro de pedidos gastronomicos', nivel_jerarquia=15))

    permisos = [
        {'codigo': 'crear_venta', 'nombre': 'Crear Venta', 'descripcion': 'Permite realizar ventas', 'modulo': 'ventas', 'requiere_autorizacion': False},
        {'codigo': 'ver_ventas', 'nombre': 'Ver Ventas', 'descripcion': 'Permite ver listado de ventas', 'modulo': 'ventas', 'requiere_autorizacion': False},
        {'codigo': 'ver_detalle_venta', 'nombre': 'Ver Detalle de Venta', 'descripcion': 'Permite ver detalles de una venta', 'modulo': 'ventas', 'requiere_autorizacion': False},
        {'codigo': 'anular_venta', 'nombre': 'Anular Venta', 'descripcion': 'Permite anular ventas completadas', 'modulo': 'ventas', 'requiere_autorizacion': True},
        {'codigo': 'editar_venta', 'nombre': 'Editar Venta', 'descripcion': 'Permite modificar ventas', 'modulo': 'ventas', 'requiere_autorizacion': True},
        {'codigo': 'aplicar_descuento', 'nombre': 'Aplicar Descuento', 'descripcion': 'Permite aplicar descuentos en ventas', 'modulo': 'ventas', 'requiere_autorizacion': False},
        {'codigo': 'aplicar_descuento_mayor', 'nombre': 'Aplicar Descuento Mayor al 10%', 'descripcion': 'Permite descuentos superiores al 10%', 'modulo': 'ventas', 'requiere_autorizacion': True},
        {'codigo': 'venta_credito', 'nombre': 'Venta a Crédito', 'descripcion': 'Permite realizar ventas a crédito', 'modulo': 'ventas', 'requiere_autorizacion': True},
        {'codigo': 'vender_sin_stock', 'nombre': 'Vender sin Stock', 'descripcion': 'Permite completar venta con stock insuficiente (requiere autorización)', 'modulo': 'ventas', 'requiere_autorizacion': True},

            {'codigo': 'ver_inventario', 'nombre': 'Ver Inventario', 'descripcion': 'Permite ver el inventario', 'modulo': 'inventario', 'requiere_autorizacion': False},
            {'codigo': 'crear_producto', 'nombre': 'Crear Producto', 'descripcion': 'Permite crear nuevos productos', 'modulo': 'inventario', 'requiere_autorizacion': False},
            {'codigo': 'editar_producto', 'nombre': 'Editar Producto', 'descripcion': 'Permite modificar productos', 'modulo': 'inventario', 'requiere_autorizacion': False},
            {'codigo': 'eliminar_producto', 'nombre': 'Eliminar Producto', 'descripcion': 'Permite eliminar productos', 'modulo': 'inventario', 'requiere_autorizacion': True},
            {'codigo': 'editar_stock', 'nombre': 'Editar Stock', 'descripcion': 'Permite ajustar stock manualmente', 'modulo': 'inventario', 'requiere_autorizacion': True},
            {'codigo': 'ajuste_rapido_stock', 'nombre': 'Ajuste Rápido de Stock', 'descripcion': 'Permite ajustar stock rápidamente sin autorización adicional', 'modulo': 'inventario', 'requiere_autorizacion': False},
            {'codigo': 'editar_precios', 'nombre': 'Editar Precios', 'descripcion': 'Permite modificar precios de productos', 'modulo': 'inventario', 'requiere_autorizacion': True},
            {'codigo': 'ver_costo_compra', 'nombre': 'Ver Costo de Compra', 'descripcion': 'Permite ver precios de compra', 'modulo': 'inventario', 'requiere_autorizacion': False},

            {'codigo': 'crear_compra', 'nombre': 'Crear Compra', 'descripcion': 'Permite registrar compras', 'modulo': 'compras', 'requiere_autorizacion': False},
            {'codigo': 'ver_compras', 'nombre': 'Ver Compras', 'descripcion': 'Permite ver listado de compras', 'modulo': 'compras', 'requiere_autorizacion': False},
            {'codigo': 'anular_compra', 'nombre': 'Anular Compra', 'descripcion': 'Permite anular compras', 'modulo': 'compras', 'requiere_autorizacion': True},
            {'codigo': 'pagar_compra', 'nombre': 'Pagar Compra', 'descripcion': 'Permite registrar pagos a proveedores', 'modulo': 'compras', 'requiere_autorizacion': False},

            {'codigo': 'abrir_caja', 'nombre': 'Abrir Caja', 'descripcion': 'Permite abrir sesión de caja', 'modulo': 'caja', 'requiere_autorizacion': False},
            {'codigo': 'cerrar_caja', 'nombre': 'Cerrar Caja', 'descripcion': 'Permite cerrar sesión de caja', 'modulo': 'caja', 'requiere_autorizacion': False},
            {'codigo': 'ver_caja', 'nombre': 'Ver Caja', 'descripcion': 'Permite ver estado de caja', 'modulo': 'caja', 'requiere_autorizacion': False},
            {'codigo': 'movimiento_caja', 'nombre': 'Movimiento de Caja', 'descripcion': 'Permite ingresos/egresos de caja', 'modulo': 'caja', 'requiere_autorizacion': False},
            {'codigo': 'editar_cierre_caja', 'nombre': 'Editar Cierre de Caja', 'descripcion': 'Permite modificar cierres de caja', 'modulo': 'caja', 'requiere_autorizacion': True},
            {'codigo': 'ver_otras_cajas', 'nombre': 'Ver Otras Cajas', 'descripcion': 'Permite ver ventas y cajas de todos los usuarios; sin este permiso solo se ven las propias', 'modulo': 'caja', 'requiere_autorizacion': False},
            {'codigo': 'enviar_caja_venta', 'nombre': 'Enviar Venta a Caja', 'descripcion': 'Permite enviar ventas registradas por vendedor para cobro en caja', 'modulo': 'caja', 'requiere_autorizacion': False},
            {'codigo': 'enviar_caja_reparacion', 'nombre': 'Enviar Reparación a Caja', 'descripcion': 'Permite enviar reparaciones a cola de cobro', 'modulo': 'caja', 'requiere_autorizacion': False},
            {'codigo': 'ver_cola_cobro', 'nombre': 'Ver Cola de Cobro', 'descripcion': 'Permite ver pendientes enviados a caja', 'modulo': 'caja', 'requiere_autorizacion': False},
            {'codigo': 'tomar_cola_cobro', 'nombre': 'Tomar Pendiente de Cobro', 'descripcion': 'Permite tomar y cobrar pendientes desde la cola de caja', 'modulo': 'caja', 'requiere_autorizacion': False},

            {'codigo': 'crear_cliente', 'nombre': 'Crear Cliente', 'descripcion': 'Permite crear nuevos clientes', 'modulo': 'clientes', 'requiere_autorizacion': False},
            {'codigo': 'editar_cliente', 'nombre': 'Editar Cliente', 'descripcion': 'Permite modificar clientes', 'modulo': 'clientes', 'requiere_autorizacion': False},
            {'codigo': 'eliminar_cliente', 'nombre': 'Eliminar Cliente', 'descripcion': 'Permite eliminar clientes', 'modulo': 'clientes', 'requiere_autorizacion': True},
            {'codigo': 'ver_clientes', 'nombre': 'Ver Clientes', 'descripcion': 'Permite ver listado de clientes', 'modulo': 'clientes', 'requiere_autorizacion': False},

            {'codigo': 'crear_proveedor', 'nombre': 'Crear Proveedor', 'descripcion': 'Permite crear proveedores', 'modulo': 'proveedores', 'requiere_autorizacion': False},
            {'codigo': 'editar_proveedor', 'nombre': 'Editar Proveedor', 'descripcion': 'Permite modificar proveedores', 'modulo': 'proveedores', 'requiere_autorizacion': False},
            {'codigo': 'eliminar_proveedor', 'nombre': 'Eliminar Proveedor', 'descripcion': 'Permite eliminar proveedores', 'modulo': 'proveedores', 'requiere_autorizacion': True},
            {'codigo': 'ver_proveedores', 'nombre': 'Ver Proveedores', 'descripcion': 'Permite ver listado de proveedores', 'modulo': 'proveedores', 'requiere_autorizacion': False},

            {'codigo': 'ver_reportes', 'nombre': 'Ver Reportes', 'descripcion': 'Permite acceder a reportes', 'modulo': 'reportes', 'requiere_autorizacion': False},
            {'codigo': 'ver_reporte_ventas', 'nombre': 'Ver Reporte de Ventas', 'descripcion': 'Permite ver reportes de ventas', 'modulo': 'reportes', 'requiere_autorizacion': False},
            {'codigo': 'ver_reporte_inventario', 'nombre': 'Ver Reporte de Inventario', 'descripcion': 'Permite ver reportes de inventario', 'modulo': 'reportes', 'requiere_autorizacion': False},
            {'codigo': 'ver_reporte_financiero', 'nombre': 'Ver Reporte Financiero', 'descripcion': 'Permite ver reportes financieros', 'modulo': 'reportes', 'requiere_autorizacion': False},
            {'codigo': 'exportar_reportes', 'nombre': 'Exportar Reportes', 'descripcion': 'Permite exportar reportes a Excel/PDF', 'modulo': 'reportes', 'requiere_autorizacion': False},

            {'codigo': 'ver_configuracion', 'nombre': 'Ver Configuración', 'descripcion': 'Permite ver configuración del sistema', 'modulo': 'configuracion', 'requiere_autorizacion': False},
            {'codigo': 'editar_configuracion', 'nombre': 'Editar Configuración', 'descripcion': 'Permite modificar configuración', 'modulo': 'configuracion', 'requiere_autorizacion': True},
            {'codigo': 'gestionar_usuarios', 'nombre': 'Gestionar Usuarios', 'descripcion': 'Permite crear/editar usuarios', 'modulo': 'configuracion', 'requiere_autorizacion': True},
            {'codigo': 'gestionar_roles', 'nombre': 'Gestionar Roles', 'descripcion': 'Permite administrar roles y permisos', 'modulo': 'configuracion', 'requiere_autorizacion': True},
            {'codigo': 'gestionar_cajas', 'nombre': 'Gestionar Cajas', 'descripcion': 'Permite crear/editar cajas', 'modulo': 'caja', 'requiere_autorizacion': True},
        {'codigo': 'usar_asistente_ia', 'nombre': 'Usar Asistente IA', 'descripcion': 'Permite usar el asistente IA interno del backoffice', 'modulo': 'asistente_ia', 'requiere_autorizacion': False},
        {'codigo': 'gestionar_asistente_ia', 'nombre': 'Gestionar Asistente IA', 'descripcion': 'Permite gestionar la configuracion del asistente IA interno', 'modulo': 'asistente_ia', 'requiere_autorizacion': True},
        {'codigo': 'ver_auditoria', 'nombre': 'Ver Auditoría', 'descripcion': 'Permite ver logs de auditoría', 'modulo': 'configuracion', 'requiere_autorizacion': False},
        {'codigo': 'ver_reparaciones', 'nombre': 'Ver Reparaciones', 'descripcion': 'Permite ver tablero y detalle de reparaciones', 'modulo': 'reparaciones', 'requiere_autorizacion': False},
        {'codigo': 'crear_reparacion', 'nombre': 'Crear Reparación', 'descripcion': 'Permite registrar recepción de equipo', 'modulo': 'reparaciones', 'requiere_autorizacion': False},
        {'codigo': 'editar_reparacion', 'nombre': 'Editar Reparación', 'descripcion': 'Permite editar reparación y costos', 'modulo': 'reparaciones', 'requiere_autorizacion': False},
        {'codigo': 'cambiar_estado_reparacion', 'nombre': 'Cambiar Estado de Reparación', 'descripcion': 'Permite cambiar estado de reparación', 'modulo': 'reparaciones', 'requiere_autorizacion': False},
        {'codigo': 'cobrar_reparacion', 'nombre': 'Cobrar Reparación', 'descripcion': 'Permite cobrar reparación en POS', 'modulo': 'reparaciones', 'requiere_autorizacion': False},
        {'codigo': 'vincular_venta_reparacion', 'nombre': 'Vincular Venta a Reparación', 'descripcion': 'Permite vincular ventas existentes a reparaciones', 'modulo': 'reparaciones', 'requiere_autorizacion': False},
        {'codigo': 'ver_recepcion_usados', 'nombre': 'Ver Compras de Usados', 'descripcion': 'Permite ver formularios de compra de equipos usados', 'modulo': 'recepcion_usados', 'requiere_autorizacion': False},
        {'codigo': 'crear_recepcion_usados', 'nombre': 'Registrar Compra de Usados', 'descripcion': 'Permite registrar compras de equipos usados y generar formulario', 'modulo': 'recepcion_usados', 'requiere_autorizacion': False},
        {'codigo': 'ver_presupuestos_empresariales', 'nombre': 'Ver Presupuestos Empresariales', 'descripcion': 'Permite ver presupuestos empresariales generados', 'modulo': 'presupuestos_empresariales', 'requiere_autorizacion': False},
        {'codigo': 'crear_presupuestos_empresariales', 'nombre': 'Crear Presupuestos Empresariales', 'descripcion': 'Permite crear presupuestos empresariales y exportarlos a PDF', 'modulo': 'presupuestos_empresariales', 'requiere_autorizacion': False},
        {'codigo': 'whatsapp_conversaciones', 'nombre': 'WhatsApp Conversaciones (beta)', 'descripcion': 'Acceso al panel de conversaciones de WhatsApp', 'modulo': 'whatsapp', 'requiere_autorizacion': False},
        {'codigo': 'crm_whatsapp', 'nombre': 'CRM WhatsApp (beta)', 'descripcion': 'Acceso al módulo CRM de WhatsApp', 'modulo': 'crm', 'requiere_autorizacion': False},
        {'codigo': 'crm_operar_como_asesor', 'nombre': 'CRM Operar como Asesor', 'descripcion': 'Permite tomar y responder chats en el panel asesor CRM', 'modulo': 'crm', 'requiere_autorizacion': False},
        {'codigo': 'agenda_acceso', 'nombre': 'Acceso Agenda', 'descripcion': 'Permite acceder al módulo Agenda', 'modulo': 'agenda', 'requiere_autorizacion': False},
        {'codigo': 'agenda_ver_todas', 'nombre': 'Ver toda la Agenda', 'descripcion': 'Permite ver actividades de todos los usuarios', 'modulo': 'agenda', 'requiere_autorizacion': False},
        {'codigo': 'agenda_crear', 'nombre': 'Crear actividades', 'descripcion': 'Permite crear nuevas actividades de agenda', 'modulo': 'agenda', 'requiere_autorizacion': False},
        {'codigo': 'agenda_editar', 'nombre': 'Editar actividades', 'descripcion': 'Permite editar actividades de agenda', 'modulo': 'agenda', 'requiere_autorizacion': False},
        {'codigo': 'agenda_completar', 'nombre': 'Completar actividades', 'descripcion': 'Permite marcar actividades como hechas', 'modulo': 'agenda', 'requiere_autorizacion': False},
        {'codigo': 'agenda_cancelar', 'nombre': 'Cancelar actividades', 'descripcion': 'Permite cancelar actividades de agenda', 'modulo': 'agenda', 'requiere_autorizacion': False},
            {'codigo': 'ver_control_empleados', 'nombre': 'Ver Control de Empleados', 'descripcion': 'Permite ver el módulo de empleados y salarios', 'modulo': 'control_empleados', 'requiere_autorizacion': False},
            {'codigo': 'gestionar_control_empleados', 'nombre': 'Gestionar Control de Empleados', 'descripcion': 'Permite crear empleados y registrar movimientos salariales', 'modulo': 'control_empleados', 'requiere_autorizacion': False},
            {'codigo': 'ver_cobranzas', 'nombre': 'Ver Cobranzas', 'descripcion': 'Permite acceder al módulo de cobranzas', 'modulo': 'cobranzas', 'requiere_autorizacion': False},
            {'codigo': 'registrar_cobro_credito', 'nombre': 'Registrar Cobro de Crédito', 'descripcion': 'Permite registrar cobros sobre cuentas por cobrar', 'modulo': 'cobranzas', 'requiere_autorizacion': False},
            {'codigo': 'anular_cobro_credito', 'nombre': 'Anular Cobro de Crédito', 'descripcion': 'Permite revertir cobros registrados en cobranzas', 'modulo': 'cobranzas', 'requiere_autorizacion': True},
            {'codigo': 'gestionar_promesa_pago', 'nombre': 'Gestionar Promesa de Pago', 'descripcion': 'Permite registrar promesas y seguimiento de cobranza', 'modulo': 'cobranzas', 'requiere_autorizacion': False},
            {'codigo': 'enviar_recordatorio_cobranza', 'nombre': 'Enviar Recordatorio de Cobranza', 'descripcion': 'Permite enviar recordatorios de cobranza', 'modulo': 'cobranzas', 'requiere_autorizacion': False},
            {'codigo': 'ver_reportes_cobranzas', 'nombre': 'Ver Reportes de Cobranzas', 'descripcion': 'Permite acceder a reportes de cobranzas', 'modulo': 'cobranzas', 'requiere_autorizacion': False},
            {'codigo': 'ver_gastos_corrientes', 'nombre': 'Ver Gastos Corrientes', 'descripcion': 'Permite ver el módulo de gastos corrientes', 'modulo': 'gastos_corrientes', 'requiere_autorizacion': False},
            {'codigo': 'crear_gastos_corrientes', 'nombre': 'Crear Gastos Corrientes', 'descripcion': 'Permite crear gastos corrientes manuales', 'modulo': 'gastos_corrientes', 'requiere_autorizacion': False},
            {'codigo': 'editar_gastos_corrientes', 'nombre': 'Editar Gastos Corrientes', 'descripcion': 'Permite editar gastos corrientes existentes', 'modulo': 'gastos_corrientes', 'requiere_autorizacion': False},
        {'codigo': 'ver_flujo_caja', 'nombre': 'Ver Flujo de Caja Proyectado', 'descripcion': 'Permite ver la tesorería inteligente y proyecciones semanales', 'modulo': 'flujo_caja', 'requiere_autorizacion': False},
        {'codigo': 'gestionar_flujo_caja', 'nombre': 'Gestionar Flujo de Caja Proyectado', 'descripcion': 'Permite preparar semanas, cargar movimientos y plantillas de tesorería', 'modulo': 'flujo_caja', 'requiere_autorizacion': False},
        {'codigo': 'registrar_pago_gasto_corriente', 'nombre': 'Registrar Pago de Gasto Corriente', 'descripcion': 'Permite registrar pagos de gastos corrientes', 'modulo': 'gastos_corrientes', 'requiere_autorizacion': False},
        {'codigo': 'anular_pago_gasto_corriente', 'nombre': 'Anular Pago de Gasto Corriente', 'descripcion': 'Permite anular pagos de gastos corrientes', 'modulo': 'gastos_corrientes', 'requiere_autorizacion': True},
        {'codigo': 'ver_reportes_gastos_corrientes', 'nombre': 'Ver Reportes de Gastos Corrientes', 'descripcion': 'Permite acceder a reportes del módulo de gastos corrientes', 'modulo': 'gastos_corrientes', 'requiere_autorizacion': False},
        {'codigo': 'gastronomia_acceso', 'nombre': 'Gastronomia - Acceso', 'descripcion': 'Permite acceder al dashboard del modo Gastronomia', 'modulo': 'gastronomia', 'requiere_autorizacion': False},
        {'codigo': 'gastronomia_menu', 'nombre': 'Gastronomia - Menu', 'descripcion': 'Permite configurar categorias, productos y modificadores gastronomicos', 'modulo': 'gastronomia', 'requiere_autorizacion': False},
        {'codigo': 'gastronomia_pos', 'nombre': 'Gastronomia - POS', 'descripcion': 'Permite tomar pedidos desde el POS touch gastronomico', 'modulo': 'gastronomia', 'requiere_autorizacion': False},
        {'codigo': 'gastronomia_cocina', 'nombre': 'Gastronomia - Cocina', 'descripcion': 'Permite operar la pantalla de cocina/KDS', 'modulo': 'gastronomia', 'requiere_autorizacion': False},
        {'codigo': 'gastronomia_caja', 'nombre': 'Gastronomia - Caja', 'descripcion': 'Permite cobrar pedidos gastronomicos', 'modulo': 'gastronomia', 'requiere_autorizacion': False},
        {'codigo': 'gastronomia_salon', 'nombre': 'Gastronomia - Salon', 'descripcion': 'Permite gestionar mesas y mover pedidos entre mesas', 'modulo': 'gastronomia', 'requiere_autorizacion': False},
        {'codigo': 'gastronomia_reportes', 'nombre': 'Gastronomia - Reportes', 'descripcion': 'Permite ver reportes y metricas gastronomicas', 'modulo': 'gastronomia', 'requiere_autorizacion': False},
    ]
    for p in permisos:
        existe = Permiso.query.filter_by(codigo=p['codigo']).first()
        if not existe:
            db.session.add(Permiso(**p))

    permiso_venta_credito = Permiso.query.filter_by(codigo='venta_credito').first()
    if permiso_venta_credito:
        # Compatibilidad con bases viejas: el permiso pudo quedar desactivado.
        if not bool(permiso_venta_credito.activo):
            permiso_venta_credito.activo = True
        if not bool(permiso_venta_credito.requiere_autorizacion):
            permiso_venta_credito.requiere_autorizacion = True
    
    # Crear caja principal
    if Caja.query.count() == 0:
        db.session.add(Caja(nombre='Caja Principal', ubicacion='Local Principal'))
    
    # Crear métodos de pago
    def _norm_metodo_pago_nombre(nombre: str) -> str:
        s = (nombre or '').strip().lower()
        s = s.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
        return ' '.join(s.split())

    metodos_defaults = [
        {'nombre': 'Efectivo', 'requiere_referencia': False, 'orden_display': 1, 'activo': True},
        {'nombre': 'Tarjeta de Débito', 'requiere_referencia': True, 'orden_display': 2, 'activo': True},
        {'nombre': 'Tarjeta de Crédito', 'requiere_referencia': True, 'orden_display': 3, 'activo': True},
        {'nombre': 'Transferencia Bancaria', 'requiere_referencia': True, 'orden_display': 4, 'activo': True},
        {'nombre': 'QR / Billetera Digital', 'requiere_referencia': True, 'orden_display': 5, 'activo': True},
        {'nombre': 'Crédito Tienda', 'requiere_referencia': False, 'orden_display': 6, 'activo': True},
    ]

    existentes = MetodoPago.query.all()
    existentes_por_norm = {_norm_metodo_pago_nombre(m.nombre): m for m in existentes}
    for md in metodos_defaults:
        k = _norm_metodo_pago_nombre(md['nombre'])
        m = existentes_por_norm.get(k)
        if not m:
            m = MetodoPago(
                nombre=md['nombre'],
                requiere_referencia=md['requiere_referencia'],
                orden_display=md['orden_display'],
                activo=bool(md.get('activo', True)),
            )
            db.session.add(m)
            existentes_por_norm[k] = m
        else:
            desired_active = bool(md.get('activo', True))
            if m.activo != desired_active:
                m.activo = desired_active
            if m.orden_display in (None, 0):
                m.orden_display = md['orden_display']

    metodo_credito_tienda = existentes_por_norm.get(_norm_metodo_pago_nombre('Crédito Tienda'))
    
    # Crear cliente Consumidor Final (ID debe ser 1)
    if Cliente.query.count() == 0:
        db.session.add(Cliente(
            id_cliente=1,
            nombre='CONSUMIDOR FINAL',
            ruc_ci='00000000-0',
            tipo='minorista'
        ))
    
    # Crear proveedor genérico si no existe
    from app.models import Proveedor
    proveedor_generico = Proveedor.query.filter_by(nombre='SIN PROVEEDOR').first()
    if not proveedor_generico:
        proveedor_generico = Proveedor(
            nombre='SIN PROVEEDOR',
            ruc='00000000-0',
            activo=True
        )
        db.session.add(proveedor_generico)
        db.session.flush()  # Para obtener el ID

    proveedor_usados = Proveedor.query.filter_by(nombre='COMPRA DE USADOS').first()
    if not proveedor_usados:
        proveedor_usados = Proveedor(
            nombre='COMPRA DE USADOS',
            ruc=None,
            direccion='Proveedor interno para compras de equipos usados',
            dias_credito=0,
            notas='Creado automáticamente para trazabilidad de compras de usados.',
            activo=True
        )
        db.session.add(proveedor_usados)
    
    # Crear categorías del rubro
    if Categoria.query.count() == 0:
        db.session.add_all([
            Categoria(nombre='Termos', descripcion='Termos de todo tipo y capacidad'),
            Categoria(nombre='Guampas', descripcion='Guampas para tereré'),
            Categoria(nombre='Mates', descripcion='Mates tradicionales y modernos'),
            Categoria(nombre='Bombillas', descripcion='Bombillas de todos los materiales'),
            Categoria(nombre='Yerbas', descripcion='Yerba mate y hierbas'),
            Categoria(nombre='Accesorios', descripcion='Accesorios varios para mate y tereré'),
            Categoria(nombre='Repuestos', descripcion='Repuestos para termos y productos'),
            Categoria(nombre='Kits y Combos', descripcion='Kits armados y promociones'),
        ])
    
    # Configuración inicial
    configuraciones = [
        ('nombre_empresa', "Pablito's Cell", 'Nombre de la empresa'),
        ('ruc_empresa', '00000000-0', 'RUC de la empresa'),
        ('direccion_empresa', 'Santa Rosa c/ 10 de Agosto', 'Dirección fiscal'),
        ('telefono_empresa', '0984758819', 'Teléfono de contacto'),
        ('moneda', 'PYG', 'Moneda del sistema'),
        ('iva_incluido', '1', 'Si los precios incluyen IVA'),
        ('stock_negativo_permitido', '0', 'Permitir vender sin stock'),
        ('pos_ocultar_selector_vendedor_cajero', '0', 'Muestra selector de vendedor/cajero en POS (desactivado: usa usuario actual)'),
        ('caja_flujo_enviado_desde_vendedor', '0', 'Habilita flujo vendedor -> caja para cobro final'),
        ('caja_alerta_pendientes_activa', '0', 'Muestra alerta visual de pendientes de cobro para cajero'),
        ('caja_exigir_cajero_para_cobro', '0', 'Bloquea cobro directo cuando el flujo de caja está activo'),
        (CLAVE_MODULO_FLUJO_CAJA, '1', DESC_MODULO_FLUJO_CAJA),
        ('control_empleados_activo', '0', 'Activa el módulo simple de control de empleados y salarios'),
        (CLAVE_VENTAS_CREDITO_ACTIVO, '0', DESC_VENTAS_CREDITO_ACTIVO),
        (CLAVE_COBRANZAS_ACTIVO, '0', DESC_COBRANZAS_ACTIVO),
        (CLAVE_VENTAS_CREDITO_METODO_PAGO_ID, str(int(metodo_credito_tienda.id_metodo_pago)) if metodo_credito_tienda else '0', DESC_VENTAS_CREDITO_METODO_PAGO_ID),
    ]
    from app.services.ia_backoffice.settings import IA_BACKOFFICE_DEFAULTS
    configuraciones.extend(
        (clave, valor, descripcion)
        for clave, (valor, descripcion) in IA_BACKOFFICE_DEFAULTS.items()
    )
    for clave, valor, descripcion in configuraciones:
        if not db.session.get(Configuracion, clave):
            db.session.add(Configuracion(clave=clave, valor=valor, descripcion=descripcion))
    if metodo_credito_tienda:
        cfg_metodo_credito = db.session.get(Configuracion, CLAVE_VENTAS_CREDITO_METODO_PAGO_ID)
        valor_actual_metodo_credito = (getattr(cfg_metodo_credito, 'valor', '') or '').strip()
        if valor_actual_metodo_credito in ('', '0'):
            if cfg_metodo_credito:
                cfg_metodo_credito.valor = str(int(metodo_credito_tienda.id_metodo_pago))
                if not cfg_metodo_credito.descripcion:
                    cfg_metodo_credito.descripcion = DESC_VENTAS_CREDITO_METODO_PAGO_ID
            else:
                db.session.add(Configuracion(
                    clave=CLAVE_VENTAS_CREDITO_METODO_PAGO_ID,
                    valor=str(int(metodo_credito_tienda.id_metodo_pago)),
                    descripcion=DESC_VENTAS_CREDITO_METODO_PAGO_ID,
                ))

    try:
        defaults = {
            'nombre_empresa': "Pablito's Cell",
            'direccion_empresa': 'Santa Rosa c/ 10 de Agosto',
            'telefono_empresa': '0984758819',
        }
        placeholders = {
            'nombre_empresa': {'', 'Mi Negocio'},
            'direccion_empresa': {'', 'Dirección del local'},
            'telefono_empresa': {''},
        }
        for clave, desired in defaults.items():
            actual = (Configuracion.obtener(clave, '') or '').strip()
            if actual in placeholders.get(clave, {''}):
                cfg = db.session.get(Configuracion, clave)
                if cfg:
                    cfg.valor = desired
                else:
                    db.session.add(Configuracion(clave=clave, valor=desired, descripcion=None))
    except Exception:
        pass
    
    if Usuario.query.count() == 0:
        admin = Usuario(
            username='admin',
            nombre_completo='Administrador del Sistema',
            id_rol=1
        )
        admin_password = os.environ.get('APP_BOOTSTRAP_ADMIN_PASSWORD')
        if admin_password is None:
            if is_production:
                admin_password = _require_safe_bootstrap_password('APP_BOOTSTRAP_ADMIN_PASSWORD', {'admin123'})
            else:
                admin_password = 'admin123'
        else:
            admin_password = admin_password.strip()
            if is_production:
                admin_password = _require_safe_bootstrap_password('APP_BOOTSTRAP_ADMIN_PASSWORD', {'admin123'})
        admin.set_password(admin_password)
        db.session.add(admin)

    root_username = (os.environ.get('APP_BOOTSTRAP_ROOT_USERNAME') or 'root').strip()
    root_user = Usuario.query.filter_by(username=root_username).first() if root_username else None
    if root_username and not root_user:
        root_user = Usuario(
            username=root_username,
            nombre_completo=os.environ.get('APP_BOOTSTRAP_ROOT_FULLNAME') or 'Root del Sistema',
            id_rol=1,
            activo=True
        )
        root_password = os.environ.get('APP_BOOTSTRAP_ROOT_PASSWORD')
        if root_password is None:
            if is_production:
                root_password = _require_safe_bootstrap_password('APP_BOOTSTRAP_ROOT_PASSWORD', {'root1409'})
            else:
                root_password = 'root1409'
        else:
            root_password = root_password.strip()
            if is_production:
                root_password = _require_safe_bootstrap_password('APP_BOOTSTRAP_ROOT_PASSWORD', {'root1409'})
        root_user.set_password(root_password)
        db.session.add(root_user)

    db.session.flush()

    if root_user and root_user.id_usuario:
        root_id_cfg = db.session.get(Configuracion, CLAVE_SYSTEM_ROOT_USER_ID)
        root_user_id = str(root_user.id_usuario)
        if root_id_cfg:
            root_id_cfg.valor = root_user_id
        else:
            db.session.add(Configuracion(
                clave=CLAVE_SYSTEM_ROOT_USER_ID,
                valor=root_user_id,
                descripcion='Usuario root exacto habilitado para switches globales',
            ))

    rol_ids = {r.nombre: r.id_rol for r in Rol.query.all()}
    permiso_ids = {p.codigo: p.id_permiso for p in Permiso.query.filter_by(activo=True).all()}

    supervisor_codigos = [
        'crear_venta', 'ver_ventas', 'ver_detalle_venta', 'aplicar_descuento', 'venta_credito',
        'vender_sin_stock',
        'ver_inventario', 'crear_producto', 'editar_producto', 'ver_costo_compra',
        'crear_compra', 'ver_compras', 'pagar_compra',
        'abrir_caja', 'cerrar_caja', 'ver_caja', 'movimiento_caja', 'ver_otras_cajas',
        'enviar_caja_venta', 'enviar_caja_reparacion', 'ver_cola_cobro', 'tomar_cola_cobro',
        'crear_cliente', 'editar_cliente', 'ver_clientes',
        'crear_proveedor', 'editar_proveedor', 'ver_proveedores',
        'ver_reportes', 'ver_reporte_ventas', 'ver_reporte_inventario', 'ver_reporte_financiero', 'exportar_reportes',
        'ver_configuracion',
        'ver_reparaciones', 'crear_reparacion', 'editar_reparacion', 'cambiar_estado_reparacion', 'cobrar_reparacion',
        'vincular_venta_reparacion',
        'ver_recepcion_usados', 'crear_recepcion_usados',
        'ver_presupuestos_empresariales', 'crear_presupuestos_empresariales',
        'whatsapp_conversaciones', 'crm_whatsapp',
        'crm_operar_como_asesor',
            'agenda_acceso', 'agenda_ver_todas', 'agenda_crear', 'agenda_editar', 'agenda_completar', 'agenda_cancelar',
            'ver_control_empleados', 'gestionar_control_empleados',
            'ver_cobranzas', 'registrar_cobro_credito', 'anular_cobro_credito',
            'gestionar_promesa_pago', 'enviar_recordatorio_cobranza', 'ver_reportes_cobranzas',
            'ver_gastos_corrientes', 'crear_gastos_corrientes', 'editar_gastos_corrientes',
            'registrar_pago_gasto_corriente', 'anular_pago_gasto_corriente',
            'ver_reportes_gastos_corrientes', 'ver_flujo_caja', 'gestionar_flujo_caja',
            'gastronomia_acceso', 'gastronomia_menu', 'gastronomia_pos',
            'gastronomia_cocina', 'gastronomia_caja', 'gastronomia_salon',
            'gastronomia_reportes',
    ]
    cajero_codigos = [
        'crear_venta', 'ver_ventas', 'ver_detalle_venta', 'aplicar_descuento',
        'vender_sin_stock',
        'ver_inventario',
        'abrir_caja', 'cerrar_caja', 'ver_caja', 'movimiento_caja',
        'ver_cola_cobro', 'tomar_cola_cobro',
        'crear_cliente', 'ver_clientes',
        'ver_proveedores',
        'ver_reparaciones', 'crear_reparacion', 'editar_reparacion', 'cambiar_estado_reparacion', 'cobrar_reparacion',
        'vincular_venta_reparacion',
            'ver_recepcion_usados', 'crear_recepcion_usados',
            'ver_presupuestos_empresariales', 'crear_presupuestos_empresariales',
            'agenda_acceso', 'agenda_ver_todas', 'agenda_crear', 'agenda_editar', 'agenda_completar', 'agenda_cancelar',
            'ver_cobranzas', 'registrar_cobro_credito',
            'ver_gastos_corrientes', 'crear_gastos_corrientes', 'editar_gastos_corrientes',
            'registrar_pago_gasto_corriente',
            'gastronomia_acceso', 'gastronomia_pos', 'gastronomia_caja',
        ]
    vendedor_codigos = [
        'ver_inventario',
        'crear_cliente', 'ver_clientes',
        'enviar_caja_venta', 'enviar_caja_reparacion',
        'ver_proveedores',
        'ver_reparaciones', 'crear_reparacion',
        'ver_recepcion_usados', 'crear_recepcion_usados',
        'ver_presupuestos_empresariales', 'crear_presupuestos_empresariales',
        'agenda_acceso', 'agenda_crear', 'agenda_editar', 'agenda_completar', 'agenda_cancelar',
        'gastronomia_acceso', 'gastronomia_pos', 'gastronomia_salon',
    ]
    tecnico_codigos = [
        'ver_clientes', 'crear_cliente',
        'ver_reparaciones', 'crear_reparacion', 'editar_reparacion',
        'cambiar_estado_reparacion',
        'agenda_acceso', 'agenda_crear', 'agenda_editar', 'agenda_completar', 'agenda_cancelar',
    ]
    cocina_codigos = ['gastronomia_acceso', 'gastronomia_cocina']
    mozo_codigos = ['gastronomia_acceso', 'gastronomia_pos', 'gastronomia_salon']
    caja_gastronomia_codigos = ['gastronomia_acceso', 'gastronomia_caja']
    auditoria_codigos = ['ver_auditoria']

    admin_id = rol_ids.get('Administrador')
    supervisor_id = rol_ids.get('Supervisor')
    cajero_id = rol_ids.get('Cajero')
    auditoria_id = rol_ids.get('Auditoria')
    vendedor_id = rol_ids.get('Vendedor')
    tecnico_id = rol_ids.get('Tecnico')
    cocina_id = rol_ids.get('Cocina')
    mozo_id = rol_ids.get('Mozo')
    caja_gastronomia_id = rol_ids.get('Caja Gastronomia')
    root_id = rol_ids.get('Root')

    if admin_id:
        for permiso_id in permiso_ids.values():
            existe = db.session.execute(
                text("SELECT 1 FROM rol_permisos WHERE id_rol = :id_rol AND id_permiso = :id_permiso LIMIT 1"),
                {"id_rol": admin_id, "id_permiso": permiso_id},
            ).first()
            if not existe:
                db.session.execute(
                    text("INSERT INTO rol_permisos (id_rol, id_permiso) VALUES (:id_rol, :id_permiso)"),
                    {"id_rol": admin_id, "id_permiso": permiso_id},
                )

    if root_id:
        for permiso_id in permiso_ids.values():
            existe = db.session.execute(
                text("SELECT 1 FROM rol_permisos WHERE id_rol = :id_rol AND id_permiso = :id_permiso LIMIT 1"),
                {"id_rol": root_id, "id_permiso": permiso_id},
            ).first()
            if not existe:
                db.session.execute(
                    text("INSERT INTO rol_permisos (id_rol, id_permiso) VALUES (:id_rol, :id_permiso)"),
                    {"id_rol": root_id, "id_permiso": permiso_id},
                )

    if root_id and root_user and root_user.id_rol != root_id:
        root_user.id_rol = root_id

    if supervisor_id:
        for codigo in supervisor_codigos:
            permiso_id = permiso_ids.get(codigo)
            if permiso_id:
                existe = db.session.execute(
                    text("SELECT 1 FROM rol_permisos WHERE id_rol = :id_rol AND id_permiso = :id_permiso LIMIT 1"),
                    {"id_rol": supervisor_id, "id_permiso": permiso_id},
                ).first()
                if not existe:
                    db.session.execute(
                        text("INSERT INTO rol_permisos (id_rol, id_permiso) VALUES (:id_rol, :id_permiso)"),
                        {"id_rol": supervisor_id, "id_permiso": permiso_id},
                    )

    if cajero_id:
        for codigo in cajero_codigos:
            permiso_id = permiso_ids.get(codigo)
            if permiso_id:
                existe = db.session.execute(
                    text("SELECT 1 FROM rol_permisos WHERE id_rol = :id_rol AND id_permiso = :id_permiso LIMIT 1"),
                    {"id_rol": cajero_id, "id_permiso": permiso_id},
                ).first()
                if not existe:
                    db.session.execute(
                        text("INSERT INTO rol_permisos (id_rol, id_permiso) VALUES (:id_rol, :id_permiso)"),
                        {"id_rol": cajero_id, "id_permiso": permiso_id},
                    )

    ver_auditoria_id = permiso_ids.get('ver_auditoria')
    if ver_auditoria_id and supervisor_id:
        db.session.execute(
            text("DELETE FROM rol_permisos WHERE id_rol = :id_rol AND id_permiso = :id_permiso"),
            {"id_rol": supervisor_id, "id_permiso": ver_auditoria_id},
        )
    if ver_auditoria_id and cajero_id:
        db.session.execute(
            text("DELETE FROM rol_permisos WHERE id_rol = :id_rol AND id_permiso = :id_permiso"),
            {"id_rol": cajero_id, "id_permiso": ver_auditoria_id},
        )

    if auditoria_id:
        for codigo in auditoria_codigos:
            permiso_id = permiso_ids.get(codigo)
            if permiso_id:
                existe = db.session.execute(
                    text("SELECT 1 FROM rol_permisos WHERE id_rol = :id_rol AND id_permiso = :id_permiso LIMIT 1"),
                    {"id_rol": auditoria_id, "id_permiso": permiso_id},
                ).first()
                if not existe:
                    db.session.execute(
                        text("INSERT INTO rol_permisos (id_rol, id_permiso) VALUES (:id_rol, :id_permiso)"),
                        {"id_rol": auditoria_id, "id_permiso": permiso_id},
                    )

    if vendedor_id:
        for codigo in vendedor_codigos:
            permiso_id = permiso_ids.get(codigo)
            if permiso_id:
                existe = db.session.execute(
                    text("SELECT 1 FROM rol_permisos WHERE id_rol = :id_rol AND id_permiso = :id_permiso LIMIT 1"),
                    {"id_rol": vendedor_id, "id_permiso": permiso_id},
                ).first()
                if not existe:
                    db.session.execute(
                        text("INSERT INTO rol_permisos (id_rol, id_permiso) VALUES (:id_rol, :id_permiso)"),
                        {"id_rol": vendedor_id, "id_permiso": permiso_id},
                    )

    if tecnico_id:
        for codigo in tecnico_codigos:
            permiso_id = permiso_ids.get(codigo)
            if permiso_id:
                existe = db.session.execute(
                    text("SELECT 1 FROM rol_permisos WHERE id_rol = :id_rol AND id_permiso = :id_permiso LIMIT 1"),
                    {"id_rol": tecnico_id, "id_permiso": permiso_id},
                ).first()
                if not existe:
                    db.session.execute(
                        text("INSERT INTO rol_permisos (id_rol, id_permiso) VALUES (:id_rol, :id_permiso)"),
                        {"id_rol": tecnico_id, "id_permiso": permiso_id},
                    )

    for role_id, codigos in (
        (cocina_id, cocina_codigos),
        (mozo_id, mozo_codigos),
        (caja_gastronomia_id, caja_gastronomia_codigos),
    ):
        if not role_id:
            continue
        for codigo in codigos:
            permiso_id = permiso_ids.get(codigo)
            if permiso_id:
                existe = db.session.execute(
                    text("SELECT 1 FROM rol_permisos WHERE id_rol = :id_rol AND id_permiso = :id_permiso LIMIT 1"),
                    {"id_rol": role_id, "id_permiso": permiso_id},
                ).first()
                if not existe:
                    db.session.execute(
                        text("INSERT INTO rol_permisos (id_rol, id_permiso) VALUES (:id_rol, :id_permiso)"),
                        {"id_rol": role_id, "id_permiso": permiso_id},
                    )

    from sqlalchemy.exc import SQLAlchemyError

    dialect = db.engine.dialect.name
    indices = [
        ("idx_auditoria_usuario", "auditoria", "id_usuario"),
        ("idx_auditoria_accion", "auditoria", "accion"),
        ("idx_auditoria_modulo", "auditoria", "modulo"),
        ("idx_auditoria_fecha", "auditoria", "fecha_accion"),
        ("idx_auditoria_referencia", "auditoria", "referencia_tipo, referencia_id"),
    ]

    for index_name, table_name, cols in indices:
        if dialect in {"mysql", "mariadb"}:
            stmt = f"CREATE INDEX {index_name} ON {table_name}({cols})"
        else:
            stmt = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({cols})"

        try:
            db.session.execute(text(stmt))
        except SQLAlchemyError as exc:
            orig = getattr(exc, "orig", None)
            orig_args = getattr(orig, "args", None) or ()
            code = orig_args[0] if orig_args else None

            if dialect in {"mysql", "mariadb"} and code in {1061}:
                continue
            raise
    
    db.session.commit()
    print("[OK] Datos base inicializados correctamente")
