"""
Seleccion de tools relevantes para reducir tokens sin quitar capacidad.
"""
import re
import unicodedata

from app.services.ia_backoffice.modulos_tools import resolver_modulo_consulta
from app.services.ia_backoffice.tools import BACKOFFICE_TOOLS


MAX_SELECTED_TOOLS = 24
RECENT_MESSAGES_FOR_ROUTING = 4

TOOL_INDEX = {tool['function']['name']: tool for tool in BACKOFFICE_TOOLS}

DEFAULT_TOOLS = [
    'dashboard_operativo_hoy',
    'buscar_entidad_backoffice',
    'ventas_resumen_periodo',
    'caja_estado_actual',
    'cobranzas_resumen',
    'inventario_resumen',
]

TOOL_GROUPS = {
    'ventas': [
        'ventas_recomendaciones_crecimiento',
        'ventas_resumen_periodo',
        'ventas_ganancia_periodo',
        'ventas_top_productos',
        'ventas_rentabilidad_productos',
        'ventas_productos_bajo_margen',
        'ventas_descuentos_periodo',
        'ventas_por_categoria',
        'ventas_tendencia',
        'ventas_ranking_mensual',
        'ventas_por_vendedor',
        'detalle_venta_documento',
        'producto_detalle_360',
    ],
    'cobranzas': [
        'cobranzas_resumen',
        'cobranzas_clientes_morosos',
        'cobranzas_proximos_vencimientos',
        'cliente_detalle_360',
    ],
    'inventario': [
        'buscar_entidad_backoffice',
        'inventario_resumen',
        'inventario_productos_reponer',
        'inventario_productos_inmovilizados',
        'producto_detalle_360',
        'ventas_top_productos',
    ],
    'gastos': [
        'gastos_resumen_periodo',
        'gastos_por_categoria',
        'gastos_vencidos',
    ],
    'caja': [
        'caja_resumen_periodo',
        'caja_estado_actual',
        'caja_anulaciones_periodo',
        'caja_cierres_recientes',
        'caja_cierre_detalle',
        'caja_cierre_diferencia',
        'caja_cierre_metodos_pago',
        'caja_cierre_movimientos',
        'caja_cierre_anulaciones',
        'detalle_venta_documento',
    ],
    'clientes': [
        'clientes_resumen_inteligencia',
        'clientes_top_valor',
        'clientes_para_contactar',
        'crm_sugerir_mensaje',
        'cliente_detalle_360',
        'cobranzas_resumen',
    ],
    'modulos': [
        'modulo_funcionamiento',
    ],
    'fidelizacion': [
        'fidelizacion_resumen',
    ],
    'empleados': [
        'empleados_resumen',
        'empleados_ausencias_periodo',
        'empleados_pagos_periodo',
        'empleados_aguinaldo_resumen',
    ],
    'reparaciones': [
        'reparaciones_resumen',
        'reparaciones_atrasadas',
        'reparaciones_por_tecnico',
        'reparaciones_fallas_frecuentes',
        'cliente_detalle_360',
    ],
    'tienda': [
        'tienda_resumen_analytics',
        'tienda_productos_mucha_vista_poca_consulta',
        'tienda_ofertas_rendimiento',
    ],
    'pedidos': [
        'pedidos_resumen',
        'pedidos_pagos_pendientes',
    ],
    'compras': [
        'compras_resumen_periodo',
        'proveedores_top',
        'proveedor_detalle_360',
    ],
    'devoluciones': [
        'devoluciones_resumen',
        'productos_mas_devueltos',
        'motivos_de_devolucion',
    ],
    'usados': [
        'usados_resumen',
        'usados_pendientes_revision',
        'usados_margen_estimado',
        'usados_por_estado',
    ],
    'presupuestos': [
        'presupuestos_resumen',
        'presupuestos_pendientes',
        'presupuestos_conversion',
        'presupuesto_detalle',
    ],
    'agenda': [
        'turnos_resumen',
        'turnos_proximos',
        'turnos_cancelados',
        'atenciones_resumen',
    ],
    'ejecutivo': [
        'ventas_recomendaciones_crecimiento',
        'dashboard_operativo_hoy',
        'hallazgos_operativos_priorizados',
        'comparar_periodos_negocio',
        'ventas_resumen_periodo',
        'caja_estado_actual',
        'cobranzas_resumen',
        'inventario_resumen',
    ],
    'metricas': [
        'metricas_explicacion_negocio',
        'metricas_comparacion_negocio',
        'metricas_resumen_operativo',
        'ventas_ganancia_periodo',
        'caja_resumen_periodo',
        'caja_cierre_diferencia',
    ],
}

INTENT_KEYWORDS = {
    'ventas': (
        'venta', 'ventas', 'vendido', 'vendio', 'vendio', 'ingreso', 'factur',
        'ganancia', 'rentabilidad', 'margen', 'descuento', 'ranking', 'top',
        'producto mas', 'mas vendido', 'categoria', 'vendedor', 'vender mas',
        'vender mejor', 'mejorar ventas', 'crecer', 'crecimiento',
        'que puedo hacer', 'que hago para vender',
    ),
    'cobranzas': ('cobranza', 'cobrar', 'cuota', 'moros', 'saldo pendiente', 'vencimiento'),
    'inventario': (
        'producto', 'productos', 'articulo', 'sku', 'codigo', 'stock',
        'inventario', 'celular', 'celulares', 'telefono', 'android',
        'iphone', 'accesorio', 'repuesto', 'color', 'blanco', 'negro',
        'dorado', 'hay', 'tenes', 'tienes',
    ),
    'gastos': ('gasto', 'gastos', 'egreso', 'vencido', 'vencidos', 'pagar'),
    'caja': ('caja', 'cierre', 'faltante', 'sobrante', 'arqueo', 'efectivo', 'anulacion'),
    'clientes': ('cliente', 'clientes', 'crm', 'contactar', 'reactivar', 'mensaje'),
    'modulos': (
        'modulo', 'módulo', 'como funciona el modulo', 'cómo funciona el módulo',
        'para que sirve el modulo', 'para que sirve el módulo',
        'que hace el modulo', 'qué hace el módulo',
    ),
    'fidelizacion': (
        'fideliz', 'programa de puntos', 'recompensa', 'recompensas',
        'canje', 'canjes', 'premio por compra', 'cliente fiel',
    ),
    'empleados': ('empleado', 'empleados', 'ausencia', 'salario', 'pago empleado', 'aguinaldo'),
    'reparaciones': ('reparacion', 'reparaciones', 'tecnico', 'falla', 'atrasada', 'atrasadas'),
    'tienda': ('tienda', 'online', 'visita', 'consulta', 'conversion', 'promocion', 'oferta'),
    'pedidos': ('pedido', 'pedidos', 'senal', 'entrega'),
    'compras': ('compra', 'compras', 'proveedor', 'proveedores'),
    'devoluciones': ('devolucion', 'devoluciones', 'devuelto', 'devueltos'),
    'usados': ('usado', 'usados', 'recepcion', 'recepciones'),
    'presupuestos': ('presupuesto', 'presupuestos', 'cotizacion', 'cotizaciones'),
    'agenda': ('agenda', 'turno', 'turnos', 'atencion', 'atenciones'),
    'ejecutivo': ('dashboard', 'negocio', 'hoy', 'hallazgo', 'alerta', 'prioridad', 'compar'),
    'metricas': (
        'ganancia neta', 'utilidad neta', 'ganancia bruta', 'utilidad bruta',
        'margen bruto', 'resultado de caja', 'resultado caja', 'flujo de caja',
        'diferencia de caja', 'cierre de caja',
    ),
    # Ayuda de uso del sistema: no necesita tools de datos
    'ayuda_sistema': (
        'como agrego', 'como creo', 'como registro', 'como cargo', 'como veo',
        'como abro', 'como cierro', 'como cambio', 'como activo', 'como habilito',
        'como uso', 'donde esta', 'donde veo', 'donde estan', 'no aparece',
        'no veo el menu', 'no encuentro', 'no tengo acceso', 'agregar usuario',
        'nuevo usuario', 'cambiar permiso', 'asignar permiso', 'abrir caja',
        'cerrar caja', 'agregar producto', 'nuevo producto', 'agregar cliente',
        'nuevo cliente', 'registrar gasto', 'registrar reparacion', 'activar modulo',
    ),
}



def _normalizar_texto(texto: str) -> str:
    texto = (texto or '').lower()
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', texto).strip()


def _texto_reciente(historial: list[dict]) -> str:
    mensajes = []
    for item in (historial or [])[-RECENT_MESSAGES_FOR_ROUTING:]:
        if isinstance(item, dict) and item.get('role') in {'user', 'assistant'}:
            mensajes.append(item.get('content') or '')
    return _normalizar_texto(' '.join(mensajes))


def _agregar_unicos(destino: list[str], nombres: list[str]) -> None:
    for nombre in nombres:
        if nombre in TOOL_INDEX and nombre not in destino:
            destino.append(nombre)


def _consulta_pide_explicar_modulo(texto_normalizado: str) -> bool:
    if not texto_normalizado:
        return False
    if 'modulo' not in texto_normalizado:
        return False
    return any(token in texto_normalizado for token in ('como funciona', 'como se usa', 'para que sirve', 'que hace'))


def nombres_tools_relevantes(historial: list[dict], max_tools: int = MAX_SELECTED_TOOLS) -> list[str]:
    texto = _texto_reciente(historial)
    seleccionadas = []

    # Si es una pregunta de ayuda de uso del sistema, no cargar tools de datos
    if any(keyword in texto for keyword in INTENT_KEYWORDS['ayuda_sistema']):
        _agregar_unicos(seleccionadas, ['modulo_funcionamiento'])
        return seleccionadas

    if _consulta_pide_explicar_modulo(texto) and resolver_modulo_consulta(texto):
        _agregar_unicos(seleccionadas, ['modulo_funcionamiento'])

    if 'que clientes' in texto or 'cuales clientes' in texto or 'clientes tienen' in texto:
        _agregar_unicos(seleccionadas, TOOL_GROUPS['clientes'])

    if any(keyword in texto for keyword in INTENT_KEYWORDS['metricas']):
        _agregar_unicos(seleccionadas, TOOL_GROUPS['metricas'])

    for grupo, keywords in INTENT_KEYWORDS.items():
        if grupo == 'metricas':
            continue
        if any(keyword in texto for keyword in keywords):
            _agregar_unicos(seleccionadas, TOOL_GROUPS[grupo])

    if 'detalle' in texto or re.search(r'\b(?:id|nro|numero)\s*\d+', texto):
        _agregar_unicos(seleccionadas, ['detalle_venta_documento', 'cliente_detalle_360', 'producto_detalle_360'])
    if any(token in texto for token in ('buscar', 'busca', 'buscame', 'encontra', 'encontrar', 'localiza')):
        _agregar_unicos(seleccionadas, ['buscar_entidad_backoffice'])
    if not seleccionadas:
        _agregar_unicos(seleccionadas, DEFAULT_TOOLS)

    limite = max(1, min(int(max_tools or MAX_SELECTED_TOOLS), len(BACKOFFICE_TOOLS)))
    return seleccionadas[:limite]


def seleccionar_tools_backoffice(historial: list[dict], max_tools: int = MAX_SELECTED_TOOLS) -> list[dict]:
    return [TOOL_INDEX[nombre] for nombre in nombres_tools_relevantes(historial, max_tools=max_tools)]
