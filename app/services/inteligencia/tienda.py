from __future__ import annotations

from app.models import TiendaConfig
from app.services.inteligencia.common import formatear_rango
from app.services.tienda_estadisticas import obtener_resumen_estadisticas_tienda


def obtener_inteligencia_tienda(periodo_actual: dict, id_cliente: int | None = None) -> dict:
    id_cliente_resuelto = resolver_id_cliente_tienda(id_cliente)
    if not id_cliente_resuelto:
        return _panel_tienda_vacio(periodo_actual)

    estadisticas = obtener_resumen_estadisticas_tienda(
        id_cliente=id_cliente_resuelto,
        desde=periodo_actual['desde'],
        hasta=periodo_actual['hasta'],
        page=1,
        per_page=8,
    )
    resumen = estadisticas['summary']
    ranking = estadisticas['ranking']
    productos_atencion = _seleccionar_productos_atencion(ranking, resumen['conversion_global'])
    horarios = estadisticas['insights']['horarios_pico'][:4]
    categorias = estadisticas['insights']['categorias_populares'][:4]
    insights = _construir_insights_tienda(productos_atencion, horarios, categorias, resumen)

    return {
        'cliente_id': id_cliente_resuelto,
        'periodo_label': formatear_rango(periodo_actual['desde'], periodo_actual['hasta']),
        'resumen': {
            'total_visitas': int(resumen['total_visitas']),
            'visitantes_unicos': int(resumen['visitantes_unicos']),
            'consultas_iniciadas': int(resumen['leads_generados']),
            'productos_con_interes': int(resumen['productos_con_visitas']),
            'conversion_global': float(resumen['conversion_global']),
            'conversion_global_label': f"{float(resumen['conversion_global']):.1f}%",
        },
        'productos_atencion': productos_atencion,
        'horarios_pico': horarios,
        'categorias_populares': categorias,
        'insights': insights,
        'hay_datos': bool(resumen['total_visitas']),
    }


def resolver_id_cliente_tienda(id_cliente: int | None = None) -> int | None:
    if id_cliente:
        return int(id_cliente)

    return None


def _seleccionar_productos_atencion(ranking: list[dict], conversion_global: float) -> list[dict]:
    candidatos = []
    for item in ranking:
        total_visitas = int(item['total_visitas'])
        leads_generados = int(item['leads_generados'])
        conversion_leads = float(item['conversion_leads'])
        if total_visitas <= 0:
            continue
        if leads_generados > 0 and conversion_leads > conversion_global:
            continue

        if leads_generados == 0:
            accion = 'Revisar precio, fotos o llamada a la acción porque atrae miradas sin consulta.'
        else:
            accion = 'Ajustar oferta y seguimiento porque recibe interés, pero convierte por debajo del promedio.'

        candidatos.append({
            'id_producto': int(item['id_producto']),
            'nombre': item['nombre'],
            'categoria': item['categoria'],
            'total_visitas': total_visitas,
            'leads_generados': leads_generados,
            'conversion_leads': conversion_leads,
            'conversion_leads_label': f'{conversion_leads:.1f}%',
            'accion': accion,
        })

    candidatos.sort(
        key=lambda item: (
            -item['total_visitas'],
            item['leads_generados'],
            item['conversion_leads'],
            item['nombre'].lower(),
        )
    )
    return candidatos[:4]


def _construir_insights_tienda(
    productos_atencion: list[dict],
    horarios: list[dict],
    categorias: list[dict],
    resumen: dict,
) -> list[dict]:
    insights = []

    if productos_atencion:
        producto = productos_atencion[0]
        insights.append({
            'prioridad': 'alta' if producto['leads_generados'] == 0 else 'media',
            'titulo': f"{producto['nombre']} concentra atención sin convertir bien",
            'detalle': (
                f"Registra {producto['total_visitas']} visitas y {producto['conversion_leads_label']} "
                f"de conversión a consulta."
            ),
            'accion': producto['accion'],
        })

    if horarios:
        horario = horarios[0]
        insights.append({
            'prioridad': 'media',
            'titulo': f"El pico de interés aparece a las {horario['hora']}",
            'detalle': f"En esa franja se registran {int(horario['total_visitas'])} aperturas de producto.",
            'accion': 'Conviene responder rápido y publicar refuerzos cerca de ese horario.',
        })

    if categorias:
        categoria = categorias[0]
        insights.append({
            'prioridad': 'baja',
            'titulo': f"{categoria['categoria']} lidera el tráfico de tienda",
            'detalle': f"Acumula {int(categoria['total_visitas'])} visitas dentro del período actual.",
            'accion': 'Destacar productos de esta categoría y revisar si la oferta acompaña ese interés.',
        })

    if not insights:
        insights.append({
            'prioridad': 'baja',
            'titulo': 'Todavía no hay datos suficientes de tienda online',
            'detalle': 'El período actual no registra visitas como para construir señales confiables.',
            'accion': 'Seguir acumulando visitas y consultas para abrir este radar.',
        })
    elif float(resumen['conversion_global']) <= 1 and int(resumen['total_visitas']) >= 10:
        insights.append({
            'prioridad': 'alta',
            'titulo': 'La conversión global de la tienda está baja',
            'detalle': f"Solo {float(resumen['conversion_global']):.1f}% de las visitas termina en consulta.",
            'accion': 'Revisar propuesta comercial y velocidad de respuesta de WhatsApp.',
        })

    prioridad_orden = {'alta': 0, 'media': 1, 'baja': 2}
    insights.sort(key=lambda item: prioridad_orden.get(item['prioridad'], 99))
    return insights[:3]


def _panel_tienda_vacio(periodo_actual: dict) -> dict:
    return {
        'cliente_id': None,
        'periodo_label': formatear_rango(periodo_actual['desde'], periodo_actual['hasta']),
        'resumen': {
            'total_visitas': 0,
            'visitantes_unicos': 0,
            'consultas_iniciadas': 0,
            'productos_con_interes': 0,
            'conversion_global': 0.0,
            'conversion_global_label': '0.0%',
        },
        'productos_atencion': [],
        'horarios_pico': [],
        'categorias_populares': [],
        'insights': [{
            'prioridad': 'baja',
            'titulo': 'Todavía no hay datos suficientes de tienda online',
            'detalle': 'El período actual no registra visitas como para construir señales confiables.',
            'accion': 'Seguir acumulando visitas y consultas para abrir este radar.',
        }],
        'hay_datos': False,
    }
