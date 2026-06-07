from __future__ import annotations

from datetime import date

from app.services.inteligencia.common import (
    armar_metrica_entera,
    armar_metrica_monetaria,
    formatear_rango,
)


def construir_panel_inteligencia(
    fecha_corte: date,
    periodo_actual: dict,
    periodo_anterior: dict,
    periodo_clave: str,
    periodo_label: str,
    periodos_disponibles: list[dict],
    facturacion_actual: float,
    facturacion_anterior: float,
    ticket_actual: float,
    ticket_anterior: float,
    clientes_activos_actual: int,
    clientes_activos_anterior: int,
    serie_clientes_activos: dict,
    clientes: dict,
    stock: dict,
    inventario: dict,
    gastronomia: dict,
    campanas: dict,
    ventas: dict,
    tienda: dict,
    acciones: list[dict],
    alertas_activas_total: int,
) -> dict:
    metrica_clientes_activos = armar_metrica_entera(
        clientes_activos_actual,
        clientes_activos_anterior,
        'Clientes activos',
    )
    metrica_clientes_activos['series'] = serie_clientes_activos

    return {
        'fecha_corte_label': fecha_corte.strftime('%d/%m/%Y'),
        'periodo_clave': periodo_clave,
        'periodo_label': periodo_label,
        'periodos_disponibles': periodos_disponibles,
        'periodo_actual_label': formatear_rango(periodo_actual['desde'], periodo_actual['hasta']),
        'periodo_anterior_label': formatear_rango(periodo_anterior['desde'], periodo_anterior['hasta']),
        'facturacion': armar_metrica_monetaria(facturacion_actual, facturacion_anterior, 'Facturación actual'),
        'ticket_promedio': armar_metrica_monetaria(ticket_actual, ticket_anterior, 'Ticket promedio'),
        'clientes_activos': metrica_clientes_activos,
        'clientes': clientes,
        'stock': stock,
        'inventario': inventario,
        'gastronomia': gastronomia,
        'campanas': campanas,
        'ventas': ventas,
        'tienda': tienda,
        'alertas_activas_total': alertas_activas_total,
        'acciones_hoy': acciones,
    }


def construir_resumen_dashboard(
    clientes: dict,
    stock: dict,
    campanas: dict,
    alertas_activas_total: int,
) -> dict:
    acciones_label = '1 acción' if alertas_activas_total == 1 else f'{alertas_activas_total} acciones'
    return {
        'clientes_para_activar': clientes['total_para_activar'],
        'alertas_activas': alertas_activas_total,
        'riesgo_stock': stock['riesgo_count'],
        'stock_inmovilizado': stock['inmovilizado_count'],
        'campanas_sugeridas': len(campanas['campanas']),
        'acciones_label': acciones_label,
    }
