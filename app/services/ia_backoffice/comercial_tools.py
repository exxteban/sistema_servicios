"""
Tools consejeras comerciales para decisiones de venta.
"""
from app.services.ia_backoffice.clientes_crm_tools import clientes_para_contactar
from app.services.ia_backoffice.inventario_tools import inventario_productos_reponer
from app.services.ia_backoffice.periods import resolver_rango
from app.services.ia_backoffice.ventas_tools import (
    ventas_ganancia_periodo,
    ventas_rentabilidad_productos,
    ventas_resumen_periodo,
    ventas_top_productos,
)


def _pct_label(value) -> str:
    if value is None:
        return 'sin comparacion'
    signo = '+' if float(value or 0) > 0 else ''
    return f'{signo}{float(value or 0):.1f}%'


def _producto_label(producto: dict) -> str:
    return f"{producto.get('nombre') or 'Producto'} ({producto.get('codigo') or 'sin codigo'})"


def ventas_recomendaciones_crecimiento(args: dict | None = None, usuario=None) -> dict:
    base_args = dict(args or {})
    if not base_args.get('periodo'):
        base_args['periodo'] = '30d'
    base_args['top_n'] = min(int(base_args.get('top_n') or 5), 8)
    rango = resolver_rango(base_args)

    resumen = ventas_resumen_periodo(base_args, usuario=usuario)
    ganancia = ventas_ganancia_periodo(base_args, usuario=usuario)
    top_productos = ventas_top_productos(base_args, usuario=usuario).get('productos') or []
    rentables = ventas_rentabilidad_productos(base_args, usuario=usuario).get('productos') or []
    reponer = inventario_productos_reponer({'top_n': 5}, usuario=usuario).get('productos') or []
    clientes = clientes_para_contactar({'top_n': 5}, usuario=usuario).get('clientes') or []

    recomendaciones = []
    variacion = resumen.get('variacion_vs_anterior_pct')
    if variacion is not None and variacion < 0:
        recomendaciones.append({
            'prioridad': 'alta',
            'accion': 'Recuperar ventas del periodo anterior',
            'motivo': f"Las ventas vienen {_pct_label(variacion)} contra el periodo comparable.",
        })
    if top_productos:
        recomendaciones.append({
            'prioridad': 'alta',
            'accion': f"Impulsar el producto mas vendido: {_producto_label(top_productos[0])}",
            'motivo': 'Ya probo demanda; conviene destacarlo en mostrador, estados y mensajes.',
        })
    if rentables:
        recomendaciones.append({
            'prioridad': 'media',
            'accion': f"Priorizar margen con {_producto_label(rentables[0])}",
            'motivo': f"Margen estimado: {rentables[0].get('margen_pct')}%.",
        })
    if clientes:
        recomendaciones.append({
            'prioridad': 'media',
            'accion': 'Contactar clientes dormidos de alto potencial',
            'motivo': f"Hay {len(clientes)} candidatos priorizados para reactivar.",
        })
    if reponer:
        recomendaciones.append({
            'prioridad': 'media',
            'accion': 'Reponer stock critico antes de promocionar',
            'motivo': f"{len(reponer)} productos estan en o debajo del minimo.",
        })
    if not recomendaciones:
        recomendaciones.append({
            'prioridad': 'media',
            'accion': 'Medir una promocion simple por 7 dias',
            'motivo': 'No se detectaron alertas fuertes; conviene probar una accion acotada y comparar.',
        })

    return {
        'periodo_label': rango['periodo_label'],
        'desde': rango['desde'].isoformat(),
        'hasta': rango['hasta'].isoformat(),
        'metricas': {
            'total_ventas': resumen.get('total_ventas'),
            'cantidad_ventas': resumen.get('cantidad_ventas'),
            'ticket_promedio': resumen.get('ticket_promedio'),
            'variacion_vs_anterior_pct': variacion,
            'ganancia_bruta_estimada': ganancia.get('ganancia_bruta_estimada'),
            'margen_bruto_pct': ganancia.get('margen_bruto_pct'),
        },
        'productos_top': top_productos[:5],
        'productos_rentables': rentables[:5],
        'productos_a_reponer': reponer[:5],
        'clientes_para_contactar': clientes[:5],
        'recomendaciones': recomendaciones[:5],
        'nota': 'Diagnostico comercial agregado en solo lectura; no ejecuta acciones.',
    }
