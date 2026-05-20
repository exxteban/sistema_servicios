from app.services.ia_backoffice.ventas_tools import (
    ventas_descuentos_periodo,
    ventas_ganancia_periodo,
    ventas_ranking_mensual,
    ventas_por_categoria,
    ventas_por_vendedor,
    ventas_productos_bajo_margen,
    ventas_rentabilidad_productos,
    ventas_resumen_periodo,
    ventas_tendencia,
    ventas_top_productos,
)
from app.services.ia_backoffice.cobranzas_tools import (
    cobranzas_clientes_morosos,
    cobranzas_proximos_vencimientos,
    cobranzas_resumen,
)
from app.services.ia_backoffice.inventario_tools import (
    inventario_productos_baja_rotacion,
    inventario_productos_inmovilizados,
    inventario_productos_reponer,
    inventario_resumen,
)
from app.services.ia_backoffice.gastos_tools import (
    gastos_por_categoria,
    gastos_resumen_periodo,
    gastos_vencidos,
)
from app.services.ia_backoffice.caja_tools import (
    caja_anulaciones_periodo,
    caja_estado_actual,
    caja_resumen_periodo,
)
from app.services.ia_backoffice.caja_cierres_tools import (
    caja_cierre_anulaciones,
    caja_cierre_detalle,
    caja_cierre_diferencia,
    caja_cierre_metodos_pago,
    caja_cierre_movimientos,
    caja_cierres_recientes,
)
from app.services.ia_backoffice.clientes_crm_tools import (
    clientes_para_contactar,
    clientes_resumen_inteligencia,
    clientes_top_valor,
    crm_sugerir_mensaje,
)
from app.services.ia_backoffice.fidelizacion_tools import fidelizacion_resumen
from app.services.ia_backoffice.modulos_tools import modulo_funcionamiento
from app.services.ia_backoffice.drilldown_insights_tools import (
    comparar_periodos_negocio,
    hallazgos_operativos_priorizados,
)
from app.services.ia_backoffice.metricas_negocio_tools import (
    metricas_comparacion_negocio,
    metricas_explicacion_negocio,
    metricas_resumen_operativo,
)
from app.services.ia_backoffice.drilldown_tools import (
    cliente_detalle_360,
    detalle_venta_documento,
    producto_detalle_360,
)
from app.services.ia_backoffice.empleados_tools import (
    empleados_aguinaldo_resumen,
    empleados_ausencias_periodo,
    empleados_pagos_periodo,
    empleados_resumen,
)
from app.services.ia_backoffice.reparaciones_tools import (
    reparaciones_atrasadas,
    reparaciones_fallas_frecuentes,
    reparaciones_por_tecnico,
    reparaciones_resumen,
)
from app.services.ia_backoffice.tienda_pedidos_tools import (
    pedidos_pagos_pendientes,
    pedidos_resumen,
    tienda_ofertas_rendimiento,
    tienda_productos_mucha_vista_poca_consulta,
    tienda_resumen_analytics,
)
from app.services.ia_backoffice.compras_proveedores_tools import (
    compras_resumen_periodo,
    proveedor_detalle_360,
    proveedores_top,
)
from app.services.ia_backoffice.devoluciones_tools import (
    devoluciones_resumen,
    motivos_de_devolucion,
    productos_mas_devueltos,
)
from app.services.ia_backoffice.usados_tools import (
    usados_margen_estimado,
    usados_pendientes_revision,
    usados_por_estado,
    usados_resumen,
)
from app.services.ia_backoffice.presupuestos_tools import (
    presupuesto_detalle,
    presupuestos_conversion,
    presupuestos_pendientes,
    presupuestos_resumen,
)
from app.services.ia_backoffice.agenda_tools import (
    atenciones_resumen,
    turnos_cancelados,
    turnos_proximos,
    turnos_resumen,
)
from app.services.ia_backoffice.executive_tools import (
    buscar_entidad_backoffice,
    dashboard_operativo_hoy,
)
from app.services.ia_backoffice.comercial_tools import ventas_recomendaciones_crecimiento
from app.services.ia_backoffice.tool_cache import guardar_tool_cache, obtener_tool_cache


BACKOFFICE_TOOL_HANDLERS = {
    'ventas_resumen_periodo': ventas_resumen_periodo,
    'ventas_ganancia_periodo': ventas_ganancia_periodo,
    'ventas_top_productos': ventas_top_productos,
    'ventas_rentabilidad_productos': ventas_rentabilidad_productos,
    'ventas_productos_bajo_margen': ventas_productos_bajo_margen,
    'ventas_descuentos_periodo': ventas_descuentos_periodo,
    'ventas_por_categoria': ventas_por_categoria,
    'ventas_tendencia': ventas_tendencia,
    'ventas_ranking_mensual': ventas_ranking_mensual,
    'ventas_por_vendedor': ventas_por_vendedor,
    'ventas_recomendaciones_crecimiento': ventas_recomendaciones_crecimiento,
    'cobranzas_resumen': cobranzas_resumen,
    'cobranzas_clientes_morosos': cobranzas_clientes_morosos,
    'cobranzas_proximos_vencimientos': cobranzas_proximos_vencimientos,
    'inventario_resumen': inventario_resumen,
    'inventario_productos_baja_rotacion': inventario_productos_baja_rotacion,
    'inventario_productos_reponer': inventario_productos_reponer,
    'inventario_productos_inmovilizados': inventario_productos_inmovilizados,
    'gastos_resumen_periodo': gastos_resumen_periodo,
    'gastos_por_categoria': gastos_por_categoria,
    'gastos_vencidos': gastos_vencidos,
    'caja_resumen_periodo': caja_resumen_periodo,
    'caja_estado_actual': caja_estado_actual,
    'caja_anulaciones_periodo': caja_anulaciones_periodo,
    'caja_cierres_recientes': caja_cierres_recientes,
    'caja_cierre_detalle': caja_cierre_detalle,
    'caja_cierre_diferencia': caja_cierre_diferencia,
    'caja_cierre_metodos_pago': caja_cierre_metodos_pago,
    'caja_cierre_movimientos': caja_cierre_movimientos,
    'caja_cierre_anulaciones': caja_cierre_anulaciones,
    'clientes_resumen_inteligencia': clientes_resumen_inteligencia,
    'clientes_top_valor': clientes_top_valor,
    'clientes_para_contactar': clientes_para_contactar,
    'crm_sugerir_mensaje': crm_sugerir_mensaje,
    'modulo_funcionamiento': modulo_funcionamiento,
    'fidelizacion_resumen': fidelizacion_resumen,
    'cliente_detalle_360': cliente_detalle_360,
    'producto_detalle_360': producto_detalle_360,
    'comparar_periodos_negocio': comparar_periodos_negocio,
    'hallazgos_operativos_priorizados': hallazgos_operativos_priorizados,
    'metricas_explicacion_negocio': metricas_explicacion_negocio,
    'metricas_comparacion_negocio': metricas_comparacion_negocio,
    'metricas_resumen_operativo': metricas_resumen_operativo,
    'detalle_venta_documento': detalle_venta_documento,
    'empleados_resumen': empleados_resumen,
    'empleados_ausencias_periodo': empleados_ausencias_periodo,
    'empleados_pagos_periodo': empleados_pagos_periodo,
    'empleados_aguinaldo_resumen': empleados_aguinaldo_resumen,
    'reparaciones_resumen': reparaciones_resumen,
    'reparaciones_atrasadas': reparaciones_atrasadas,
    'reparaciones_por_tecnico': reparaciones_por_tecnico,
    'reparaciones_fallas_frecuentes': reparaciones_fallas_frecuentes,
    'tienda_resumen_analytics': tienda_resumen_analytics,
    'tienda_productos_mucha_vista_poca_consulta': tienda_productos_mucha_vista_poca_consulta,
    'tienda_ofertas_rendimiento': tienda_ofertas_rendimiento,
    'pedidos_resumen': pedidos_resumen,
    'pedidos_pagos_pendientes': pedidos_pagos_pendientes,
    'compras_resumen_periodo': compras_resumen_periodo,
    'proveedores_top': proveedores_top,
    'proveedor_detalle_360': proveedor_detalle_360,
    'devoluciones_resumen': devoluciones_resumen,
    'productos_mas_devueltos': productos_mas_devueltos,
    'motivos_de_devolucion': motivos_de_devolucion,
    'usados_resumen': usados_resumen,
    'usados_pendientes_revision': usados_pendientes_revision,
    'usados_margen_estimado': usados_margen_estimado,
    'usados_por_estado': usados_por_estado,
    'presupuestos_resumen': presupuestos_resumen,
    'presupuestos_pendientes': presupuestos_pendientes,
    'presupuestos_conversion': presupuestos_conversion,
    'presupuesto_detalle': presupuesto_detalle,
    'turnos_resumen': turnos_resumen,
    'turnos_proximos': turnos_proximos,
    'turnos_cancelados': turnos_cancelados,
    'atenciones_resumen': atenciones_resumen,
    'buscar_entidad_backoffice': buscar_entidad_backoffice,
    'dashboard_operativo_hoy': dashboard_operativo_hoy,
}


def _puede_consultar_ventas(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(
        usuario.tiene_permiso('ver_ventas')
        or usuario.tiene_permiso('ver_reporte_ventas')
    )


def _puede_consultar_cobranzas(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_cobranzas') or usuario.tiene_permiso('ver_reportes_cobranzas'))


def _puede_consultar_inventario(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_inventario') or usuario.tiene_permiso('ver_reporte_inventario'))


def _puede_consultar_gastos(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_gastos_corrientes') or usuario.tiene_permiso('ver_reportes_gastos_corrientes'))


def _puede_consultar_caja(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_caja') or usuario.tiene_permiso('ver_otras_cajas'))


def _puede_consultar_clientes(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_clientes'))


def _puede_consultar_crm(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_clientes') and usuario.tiene_permiso('crm_whatsapp'))


def _puede_consultar_fidelizacion(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(_puede_consultar_clientes(usuario) or usuario.tiene_permiso('crear_venta'))


def _puede_consultar_modulos_funcionales(usuario) -> bool:
    return bool(usuario and getattr(usuario, 'is_authenticated', False))


def _puede_consultar_empleados(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_control_empleados'))


def _puede_consultar_reparaciones(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_reparaciones'))


def _puede_consultar_tienda(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_reportes'))


def _puede_consultar_pedidos(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_clientes'))


def _puede_consultar_compras(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_compras') or usuario.tiene_permiso('ver_inventario'))


def _puede_consultar_devoluciones(usuario) -> bool:
    return bool(_puede_consultar_ventas(usuario) or _puede_consultar_caja(usuario))


def _puede_consultar_usados(usuario) -> bool:
    return bool(_puede_consultar_compras(usuario) or _puede_consultar_inventario(usuario))


def _puede_consultar_presupuestos(usuario) -> bool:
    return bool(_puede_consultar_ventas(usuario) or _puede_consultar_clientes(usuario))


def _puede_consultar_agenda(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if getattr(usuario, 'es_admin', lambda: False)():
        return True
    return bool(usuario.tiene_permiso('ver_agenda') or usuario.tiene_permiso('usar_asistente_ia'))


def _puede_consultar_drilldown_cliente(usuario) -> bool:
    return bool(
        _puede_consultar_clientes(usuario)
        or _puede_consultar_ventas(usuario)
        or _puede_consultar_cobranzas(usuario)
        or _puede_consultar_reparaciones(usuario)
    )


def _puede_consultar_drilldown_producto(usuario) -> bool:
    return bool(_puede_consultar_inventario(usuario) or _puede_consultar_ventas(usuario))


def _puede_consultar_drilldown_comparacion(usuario) -> bool:
    return bool(
        _puede_consultar_ventas(usuario)
        or _puede_consultar_cobranzas(usuario)
        or _puede_consultar_inventario(usuario)
    )


def _puede_consultar_drilldown_hallazgos(usuario) -> bool:
    return bool(
        _puede_consultar_ventas(usuario)
        or _puede_consultar_cobranzas(usuario)
        or _puede_consultar_inventario(usuario)
        or _puede_consultar_gastos(usuario)
        or _puede_consultar_clientes(usuario)
        or _puede_consultar_caja(usuario)
    )


def _puede_consultar_metricas_conceptuales(usuario) -> bool:
    return bool(usuario and getattr(usuario, 'is_authenticated', False))


def _puede_consultar_metricas_operativas(usuario) -> bool:
    return bool(
        _puede_consultar_ventas(usuario)
        or _puede_consultar_caja(usuario)
        or _puede_consultar_gastos(usuario)
    )


def ejecutar_tool_backoffice(nombre: str, argumentos: dict | None = None, usuario=None) -> dict:
    handler = BACKOFFICE_TOOL_HANDLERS.get(nombre)
    if not handler:
        return {'ok': False, 'error': 'tool_no_encontrada', 'tool': nombre}
    if nombre.startswith('ventas_') and not _puede_consultar_ventas(usuario):
        return {'ok': False, 'error': 'sin_permiso_ventas', 'tool': nombre}
    if nombre.startswith('cobranzas_') and not _puede_consultar_cobranzas(usuario):
        return {'ok': False, 'error': 'sin_permiso_cobranzas', 'tool': nombre}
    if nombre.startswith('inventario_') and not _puede_consultar_inventario(usuario):
        return {'ok': False, 'error': 'sin_permiso_inventario', 'tool': nombre}
    if nombre.startswith('gastos_') and not _puede_consultar_gastos(usuario):
        return {'ok': False, 'error': 'sin_permiso_gastos', 'tool': nombre}
    if nombre.startswith('caja_') and not _puede_consultar_caja(usuario):
        return {'ok': False, 'error': 'sin_permiso_caja', 'tool': nombre}
    if nombre.startswith('clientes_') and not _puede_consultar_clientes(usuario):
        return {'ok': False, 'error': 'sin_permiso_clientes', 'tool': nombre}
    if nombre.startswith('crm_') and not _puede_consultar_crm(usuario):
        return {'ok': False, 'error': 'sin_permiso_crm', 'tool': nombre}
    if nombre == 'modulo_funcionamiento' and not _puede_consultar_modulos_funcionales(usuario):
        return {'ok': False, 'error': 'sin_permiso_modulos_funcionales', 'tool': nombre}
    if nombre == 'fidelizacion_resumen' and not _puede_consultar_fidelizacion(usuario):
        return {'ok': False, 'error': 'sin_permiso_fidelizacion', 'tool': nombre}
    if nombre.startswith('empleados_') and not _puede_consultar_empleados(usuario):
        return {'ok': False, 'error': 'sin_permiso_empleados', 'tool': nombre}
    if nombre.startswith('reparaciones_') and not _puede_consultar_reparaciones(usuario):
        return {'ok': False, 'error': 'sin_permiso_reparaciones', 'tool': nombre}
    if nombre.startswith('tienda_') and not _puede_consultar_tienda(usuario):
        return {'ok': False, 'error': 'sin_permiso_tienda', 'tool': nombre}
    if nombre.startswith('pedidos_') and not _puede_consultar_pedidos(usuario):
        return {'ok': False, 'error': 'sin_permiso_pedidos', 'tool': nombre}
    if (nombre.startswith('compras_') or nombre.startswith('proveedor')) and not _puede_consultar_compras(usuario):
        return {'ok': False, 'error': 'sin_permiso_compras', 'tool': nombre}
    if (nombre.startswith('devoluciones_') or nombre in {'productos_mas_devueltos', 'motivos_de_devolucion'}) and not _puede_consultar_devoluciones(usuario):
        return {'ok': False, 'error': 'sin_permiso_devoluciones', 'tool': nombre}
    if nombre.startswith('usados_') and not _puede_consultar_usados(usuario):
        return {'ok': False, 'error': 'sin_permiso_usados', 'tool': nombre}
    if nombre.startswith('presupuesto') and not _puede_consultar_presupuestos(usuario):
        return {'ok': False, 'error': 'sin_permiso_presupuestos', 'tool': nombre}
    if (nombre.startswith('turnos_') or nombre == 'atenciones_resumen') and not _puede_consultar_agenda(usuario):
        return {'ok': False, 'error': 'sin_permiso_agenda', 'tool': nombre}
    if nombre == 'buscar_entidad_backoffice' and not _puede_consultar_drilldown_hallazgos(usuario):
        return {'ok': False, 'error': 'sin_permiso_busqueda_backoffice', 'tool': nombre}
    if nombre == 'dashboard_operativo_hoy' and not _puede_consultar_drilldown_hallazgos(usuario):
        return {'ok': False, 'error': 'sin_permiso_dashboard_operativo', 'tool': nombre}
    if nombre == 'cliente_detalle_360' and not _puede_consultar_drilldown_cliente(usuario):
        return {'ok': False, 'error': 'sin_permiso_cliente_detalle', 'tool': nombre}
    if nombre == 'producto_detalle_360' and not _puede_consultar_drilldown_producto(usuario):
        return {'ok': False, 'error': 'sin_permiso_producto_detalle', 'tool': nombre}
    if nombre == 'comparar_periodos_negocio' and not _puede_consultar_drilldown_comparacion(usuario):
        return {'ok': False, 'error': 'sin_permiso_comparar_periodos', 'tool': nombre}
    if nombre == 'hallazgos_operativos_priorizados' and not _puede_consultar_drilldown_hallazgos(usuario):
        return {'ok': False, 'error': 'sin_permiso_hallazgos_operativos', 'tool': nombre}
    if nombre in {'metricas_explicacion_negocio', 'metricas_comparacion_negocio'} and not _puede_consultar_metricas_conceptuales(usuario):
        return {'ok': False, 'error': 'sin_permiso_metricas_conceptuales', 'tool': nombre}
    if nombre == 'metricas_resumen_operativo' and not _puede_consultar_metricas_operativas(usuario):
        return {'ok': False, 'error': 'sin_permiso_metricas_operativas', 'tool': nombre}
    if nombre == 'detalle_venta_documento' and not _puede_consultar_ventas(usuario):
        return {'ok': False, 'error': 'sin_permiso_detalle_venta', 'tool': nombre}
    if nombre == 'ventas_recomendaciones_crecimiento' and not (
        _puede_consultar_ventas(usuario)
        and _puede_consultar_inventario(usuario)
        and _puede_consultar_clientes(usuario)
    ):
        return {'ok': False, 'error': 'sin_permiso_recomendaciones_crecimiento', 'tool': nombre}
    try:
        args = argumentos or {}
        cacheado = obtener_tool_cache(nombre, args, usuario)
        if cacheado is not None:
            return {'ok': True, 'tool': nombre, 'data': cacheado}
        data = handler(args, usuario=usuario)
        guardar_tool_cache(nombre, args, usuario, data)
        return {'ok': True, 'tool': nombre, 'data': data}
    except Exception as exc:
        return {'ok': False, 'error': type(exc).__name__, 'tool': nombre}
