from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func

from app import db
from app.models import Categoria, DetalleVenta, Producto, Venta
from app.services.inteligencia.common import (
    SEMANAS_TENDENCIA_VENTAS,
    calcular_variacion,
    formatear_moneda,
    formatear_rango,
)
from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local


def obtener_inteligencia_ventas(fecha_corte: date, periodo_actual: dict, periodo_anterior: dict) -> dict:
    resumen_actual = _obtener_resumen_periodo(periodo_actual['desde'], periodo_actual['hasta'])
    resumen_anterior = _obtener_resumen_periodo(periodo_anterior['desde'], periodo_anterior['hasta'])
    categorias_actuales = _obtener_categorias_periodo(periodo_actual['desde'], periodo_actual['hasta'])
    categorias_anteriores = _obtener_categorias_periodo(periodo_anterior['desde'], periodo_anterior['hasta'])
    tendencia = _obtener_tendencia_semanal(fecha_corte)
    categorias = _combinar_categorias(categorias_actuales, categorias_anteriores)
    insights = _construir_insights(resumen_actual, resumen_anterior, categorias)

    return {
        'cantidad_ventas': _armar_metrica_cantidad_ventas(resumen_actual, resumen_anterior),
        'salud': _construir_salud_comercial(resumen_actual, resumen_anterior),
        'categorias': categorias,
        'tendencia': tendencia,
        'insights': insights,
        'periodo_label': formatear_rango(periodo_actual['desde'], periodo_actual['hasta']),
    }


def _obtener_resumen_periodo(desde: date, hasta: date) -> dict:
    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde, hasta)
    fila = (
        db.session.query(
            func.coalesce(func.sum(Venta.total), 0).label('facturacion'),
            func.count(Venta.id_venta).label('cantidad_ventas'),
        )
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .first()
    )
    facturacion = float(getattr(fila, 'facturacion', 0) or 0)
    cantidad_ventas = int(getattr(fila, 'cantidad_ventas', 0) or 0)
    ticket_promedio = facturacion / cantidad_ventas if cantidad_ventas > 0 else 0.0
    return {
        'facturacion': facturacion,
        'cantidad_ventas': cantidad_ventas,
        'ticket_promedio': ticket_promedio,
    }


def _obtener_categorias_periodo(desde: date, hasta: date) -> list[dict]:
    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde, hasta)
    filas = (
        db.session.query(
            Categoria.nombre.label('categoria'),
            func.coalesce(func.sum(DetalleVenta.subtotal), 0).label('facturacion'),
            func.coalesce(func.sum(DetalleVenta.cantidad), 0).label('unidades'),
        )
        .join(Producto, Producto.id_categoria == Categoria.id_categoria)
        .join(DetalleVenta, DetalleVenta.id_producto == Producto.id_producto)
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .group_by(Categoria.id_categoria, Categoria.nombre)
        .order_by(func.sum(DetalleVenta.subtotal).desc(), Categoria.nombre.asc())
        .all()
    )
    return [
        {
            'categoria': (fila.categoria or 'Sin categoría').strip() or 'Sin categoría',
            'facturacion': float(getattr(fila, 'facturacion', 0) or 0),
            'unidades': int(getattr(fila, 'unidades', 0) or 0),
        }
        for fila in filas
    ]


def _obtener_tendencia_semanal(fecha_corte: date, semanas: int = SEMANAS_TENDENCIA_VENTAS) -> list[dict]:
    bloques = _armar_bloques_tendencia(fecha_corte, semanas)
    if not bloques:
        return []

    fecha_minima = bloques[0]['desde']
    fecha_maxima = bloques[-1]['hasta']
    ventas_por_fecha = _obtener_ventas_por_fecha(fecha_minima, fecha_maxima)

    for bloque in bloques:
        bloque['facturacion'] = _sumar_facturacion_bloque(ventas_por_fecha, bloque['desde'], bloque['hasta'])
        bloque['cantidad_ventas'] = _sumar_cantidad_bloque(ventas_por_fecha, bloque['desde'], bloque['hasta'])

    for posicion, bloque in enumerate(bloques):
        previo = bloques[posicion - 1] if posicion > 0 else None
        variacion = calcular_variacion(
            bloque['facturacion'],
            previo['facturacion'] if previo else 0,
        )
        bloque['rango_label'] = formatear_rango(bloque['desde'], bloque['hasta'])
        bloque['facturacion_label'] = formatear_moneda(bloque['facturacion'])
        bloque['variacion_label'] = 'Inicio de referencia' if previo is None else variacion['label']
        bloque['direccion'] = 'flat' if previo is None else variacion['direccion']

    return bloques


def _armar_bloques_tendencia(fecha_corte: date, semanas: int) -> list[dict]:
    bloques = []
    for indice in range(semanas - 1, -1, -1):
        hasta = fecha_corte - timedelta(days=indice * 7)
        desde = hasta - timedelta(days=6)
        bloques.append({'desde': desde, 'hasta': hasta})
    return bloques


def _obtener_ventas_por_fecha(desde: date, hasta: date) -> dict[date, dict]:
    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde, hasta)
    filas = (
        db.session.query(Venta.fecha_venta, Venta.total)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .all()
    )
    ventas_por_fecha = defaultdict(lambda: {'facturacion': 0.0, 'cantidad_ventas': 0})
    for fila in filas:
        fecha_local = utc_naive_to_local(fila.fecha_venta)
        if not fecha_local:
            continue
        item = ventas_por_fecha[fecha_local.date()]
        item['facturacion'] += float(fila.total or 0)
        item['cantidad_ventas'] += 1
    return dict(ventas_por_fecha)


def _sumar_facturacion_bloque(ventas_por_fecha: dict[date, dict], desde: date, hasta: date) -> float:
    total = 0.0
    cursor = desde
    while cursor <= hasta:
        total += float(ventas_por_fecha.get(cursor, {}).get('facturacion', 0) or 0)
        cursor += timedelta(days=1)
    return total


def _sumar_cantidad_bloque(ventas_por_fecha: dict[date, dict], desde: date, hasta: date) -> int:
    total = 0
    cursor = desde
    while cursor <= hasta:
        total += int(ventas_por_fecha.get(cursor, {}).get('cantidad_ventas', 0) or 0)
        cursor += timedelta(days=1)
    return total


def _combinar_categorias(categorias_actuales: list[dict], categorias_anteriores: list[dict]) -> list[dict]:
    total_actual = sum(item['facturacion'] for item in categorias_actuales)
    anteriores_por_nombre = {item['categoria']: item for item in categorias_anteriores}
    categorias = []

    for categoria in categorias_actuales[:5]:
        categoria_anterior = anteriores_por_nombre.get(categoria['categoria'], {})
        variacion = calcular_variacion(categoria['facturacion'], categoria_anterior.get('facturacion', 0))
        participacion = (categoria['facturacion'] / total_actual * 100) if total_actual > 0 else 0.0
        categorias.append({
            'nombre': categoria['categoria'],
            'facturacion': categoria['facturacion'],
            'facturacion_label': formatear_moneda(categoria['facturacion']),
            'unidades': categoria['unidades'],
            'participacion_label': f'{participacion:.1f}%',
            'variacion_label': variacion['label'],
            'direccion': variacion['direccion'],
            'accion': _sugerir_accion_categoria(participacion, variacion['direccion']),
        })

    return categorias


def _construir_salud_comercial(resumen_actual: dict, resumen_anterior: dict) -> dict:
    variacion_facturacion = calcular_variacion(resumen_actual['facturacion'], resumen_anterior['facturacion'])
    variacion_ticket = calcular_variacion(resumen_actual['ticket_promedio'], resumen_anterior['ticket_promedio'])

    if variacion_facturacion['direccion'] == 'down':
        mensaje = 'La facturación se enfrió frente al período anterior.'
        accion = 'Revisar mezcla de venta y empujar categorías que más sostienen ingreso.'
    elif variacion_facturacion['direccion'] == 'up':
        mensaje = 'La facturación viene mejor que en el tramo anterior.'
        accion = 'Aprovechar el envión reforzando las categorías que ya están traccionando.'
    else:
        mensaje = 'La facturación se mantiene estable en comparación con el período anterior.'
        accion = 'Buscar una categoría líder para mover el ticket sin perder volumen.'

    return {
        'mensaje': mensaje,
        'detalle': (
            f"Ventas cerradas: {resumen_actual['cantidad_ventas']} · "
            f"Facturación: {formatear_moneda(resumen_actual['facturacion'])} · "
            f"Ticket promedio: {formatear_moneda(resumen_actual['ticket_promedio'])}"
        ),
        'facturacion_variacion_label': variacion_facturacion['label'],
        'facturacion_direccion': variacion_facturacion['direccion'],
        'ticket_variacion_label': variacion_ticket['label'],
        'ticket_direccion': variacion_ticket['direccion'],
        'accion': accion,
    }


def _construir_insights(resumen_actual: dict, resumen_anterior: dict, categorias: list[dict]) -> list[dict]:
    insights = []
    variacion_facturacion = calcular_variacion(resumen_actual['facturacion'], resumen_anterior['facturacion'])
    variacion_ticket = calcular_variacion(resumen_actual['ticket_promedio'], resumen_anterior['ticket_promedio'])

    if variacion_facturacion['direccion'] == 'down':
        insights.append({
            'prioridad': 'alta',
            'titulo': 'La facturación cayó frente al tramo anterior',
            'detalle': f"Se mueve {variacion_facturacion['label']} y conviene revisar rápido qué categorías perdieron peso.",
            'accion': 'Revisar mix de productos y reforzar la categoría más estable.',
        })

    if variacion_ticket['direccion'] == 'down':
        insights.append({
            'prioridad': 'media',
            'titulo': 'El ticket promedio se achicó',
            'detalle': f"El ticket muestra {variacion_ticket['label']} aunque siga habiendo ventas cerradas.",
            'accion': 'Empujar productos de ticket medio/alto o combos simples.',
        })

    if categorias:
        categoria_lider = categorias[0]
        insights.append({
            'prioridad': 'media' if categoria_lider['direccion'] == 'down' else 'baja',
            'titulo': f"{categoria_lider['nombre']} sostiene el ingreso actual",
            'detalle': (
                f"Aporta {categoria_lider['participacion_label']} del total del período "
                f"con {categoria_lider['facturacion_label']} vendidos."
            ),
            'accion': categoria_lider['accion'],
        })

    if not insights:
        insights.append({
            'prioridad': 'baja',
            'titulo': 'No hay señales fuertes de ventas para corregir hoy',
            'detalle': 'El comportamiento comercial luce parejo frente al período anterior.',
            'accion': 'Mantener seguimiento de tendencia y categorías líderes.',
        })

    prioridad_orden = {'alta': 0, 'media': 1, 'baja': 2}
    insights.sort(key=lambda item: prioridad_orden.get(item['prioridad'], 99))
    return insights[:3]


def _armar_metrica_cantidad_ventas(resumen_actual: dict, resumen_anterior: dict) -> dict:
    variacion = calcular_variacion(resumen_actual['cantidad_ventas'], resumen_anterior['cantidad_ventas'])
    return {
        'titulo': 'Ventas cerradas',
        'actual': resumen_actual['cantidad_ventas'],
        'actual_label': str(resumen_actual['cantidad_ventas']),
        'anterior_label': str(resumen_anterior['cantidad_ventas']),
        'variacion_label': variacion['label'],
        'direccion': variacion['direccion'],
    }


def _sugerir_accion_categoria(participacion: float, direccion: str) -> str:
    if direccion == 'down':
        return 'Reforzar esta categoría antes de que siga perdiendo peso.'
    if participacion >= 45:
        return 'Sostener stock y visibilidad porque hoy empuja gran parte del ingreso.'
    return 'Probar una acción comercial puntual para que siga ganando participación.'
