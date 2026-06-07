"""Recomendaciones de promociones para franjas de baja demanda."""
from __future__ import annotations

from collections import defaultdict

from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local
from gastronomia.models import GastronomiaPedidoPago


MIN_HORAS_OBSERVADAS = 4


def promociones_horario_bajo(cliente_id: int, periodo: dict, productos_top: list[dict], limite: int = 4) -> list[dict]:
    horas = _horas_con_venta(cliente_id, periodo)
    if len(horas) < MIN_HORAS_OBSERVADAS:
        return []

    promedio = sum(item['pedidos'] for item in horas.values()) / len(horas)
    umbral = max(1, promedio * 0.55)
    productos = productos_top[:2] or [{'nombre': 'producto lider', 'accion': 'Usarlo como ancla para promo.'}]
    candidatos = [item for item in horas.values() if item['pedidos'] <= umbral]
    candidatos.sort(key=lambda item: (item['pedidos'], item['total'], item['hora']))
    return [
        _sugerencia(item, productos[index % len(productos)], promedio)
        for index, item in enumerate(candidatos[:max(1, min(10, int(limite or 4)))])
    ]


def _horas_con_venta(cliente_id: int, periodo: dict) -> dict[int, dict]:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    pagos = GastronomiaPedidoPago.query.filter(
        GastronomiaPedidoPago.cliente_id == int(cliente_id),
        GastronomiaPedidoPago.fecha_pago >= inicio,
        GastronomiaPedidoPago.fecha_pago < fin,
    ).all()
    horas = defaultdict(lambda: {'hora': 0, 'pedidos': 0, 'total': 0.0})
    for pago in pagos:
        fecha_local = utc_naive_to_local(pago.fecha_pago)
        if not fecha_local:
            continue
        item = horas[fecha_local.hour]
        item['hora'] = fecha_local.hour
        item['pedidos'] += 1
        item['total'] += float(pago.total_cobrado or 0)
    return dict(horas)


def _sugerencia(hora: dict, producto: dict, promedio: float) -> dict:
    hora_label = f"{int(hora['hora']):02d}:00"
    nombre_producto = producto.get('nombre') or 'producto lider'
    return {
        'hora': int(hora['hora']),
        'hora_label': hora_label,
        'pedidos': int(hora['pedidos'] or 0),
        'promedio_pedidos': round(promedio, 1),
        'producto_sugerido': nombre_producto,
        'titulo': f'Promo suave a las {hora_label}',
        'detalle': f"La franja registra {int(hora['pedidos'] or 0)} pedido(s), por debajo del promedio de {promedio:.1f}.",
        'accion': f'Probar combo o beneficio corto con {nombre_producto} en esta franja baja.',
    }
