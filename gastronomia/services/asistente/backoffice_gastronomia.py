"""Version gastronomica de las tools de ventas por producto del Asistente IA interno (backoffice).

En gastronomia cada venta guarda el plato como servicio (DetalleVenta.id_servicio), asi que las tools del
backoffice que cruzan DetalleVenta.id_producto devuelven vacio (ranking, categorias) o costo 0 (ganancia
con margen 100%). Con gastronomia activa, el despacho del backoffice usa estas versiones: mismo formato de
salida, suman los platos (pedidos cobrados, costo de recetas) a lo que ya devuelve la original. Afecta al chat de arriba, a los insights
diarios y al panel del asistente de configuracion.
"""
from __future__ import annotations

from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.utils.helpers import utc_bounds_for_local_dates
from gastronomia.services.costos_service import costo_total_por_plato
from gastronomia.services.inteligencia_service import _categorias_top
from gastronomia.services.reportes_service import productos_mas_vendidos

METODO = 'Datos de pedidos cobrados de gastronomia; costo estimado con las recetas actuales de cada plato.'


def _cliente_id() -> int | None:
    from gastronomia.services.access import cliente_id_actual_gastronomia

    try:
        return cliente_id_actual_gastronomia()
    except Exception:  # noqa: BLE001 - sin contexto de gastronomia se usa la tool original
        return None


def _platos(cliente_id: int, desde, hasta) -> list[dict]:
    inicio, fin = utc_bounds_for_local_dates(desde, hasta)
    platos = productos_mas_vendidos(cliente_id, inicio, fin, limite=None)
    costos = costo_total_por_plato(cliente_id, sorted({int(p['producto_id']) for p in platos}))
    filas = []
    for p in platos:
        unitario = float(costos.get(int(p['producto_id']), 0.0))
        ingreso = float(p['total'] or 0)
        costo = unitario * int(p['cantidad'] or 0)
        ganancia = ingreso - costo
        filas.append({
            'id_producto': p['producto_id'],
            'codigo': '',
            'nombre': p['nombre_producto'],
            'categoria': '',
            'unidades': int(p['cantidad'] or 0),
            'ingreso': ingreso,
            'costo_estimado': costo,
            'ganancia_estimada': ganancia,
            'margen_pct': round(ganancia / ingreso * 100, 2) if ingreso else None,
            'descuento_lineas': 0.0,
            'sin_costo_cargado': unitario <= 0,
        })
    return filas


def _con_platos(cid: int, args: dict, original, campos: tuple | None = None) -> tuple[dict, list[dict], int]:
    """Resultado original (productos de inventario vendidos, si los hay) + platos del menu, sin top_n aplicado."""
    data = original({**args, 'top_n': 100})
    rango, top_n = resolver_rango(args), normalizar_top_n(args.get('top_n'))
    platos = _platos(cid, rango['desde'], rango['hasta'])
    if campos:
        platos = [{k: f[k] for k in campos} for f in platos]
    return data, list(data.get('productos') or []) + platos, top_n


def _top_productos(cid: int, args: dict, original) -> dict:
    data, filas, top_n = _con_platos(cid, args, original, ('id_producto', 'codigo', 'nombre', 'unidades', 'ingreso'))
    filas.sort(key=lambda f: (-float(f['ingreso'] or 0), f['nombre'] or ''))
    return {**data, 'top_n': top_n, 'productos': filas[:top_n]}


def _rentabilidad(cid: int, args: dict, original) -> dict:
    data, filas, top_n = _con_platos(cid, args, original)
    filas.sort(key=lambda f: -float(f['ganancia_estimada'] or 0))
    return {**data, 'top_n': top_n, 'productos': filas[:top_n], 'metodo_calculo': METODO}


def _bajo_margen(cid: int, args: dict, original) -> dict:
    data, filas, top_n = _con_platos(cid, args, original)
    filas = [f for f in filas if float(f['ingreso'] or 0) > 0]
    filas.sort(key=lambda f: (f['margen_pct'] if f['margen_pct'] is not None else 999, -float(f['ingreso'] or 0)))
    return {**data, 'top_n': top_n, 'productos': filas[:top_n], 'metodo_calculo': METODO}


def _variacion(actual: float, previo: float):
    return round((actual - previo) / previo * 100, 2) if previo else None


def _por_categoria(cid: int, args: dict, original) -> dict:
    data = original({**args, 'top_n': 100})
    rango, top_n = resolver_rango(args), normalizar_top_n(args.get('top_n'))
    periodo_anterior = {'desde': rango['anterior_desde'], 'hasta': rango['anterior_hasta']}
    previas = {c['nombre']: float(c['total'] or 0) for c in _categorias_top(cid, periodo_anterior, limite=20)}
    filas = [dict(c) for c in data.get('categorias') or []] + [{
        'categoria': c['nombre'],
        'unidades': c['cantidad'],
        'ingreso': c['total'],
        'variacion_vs_anterior_pct': _variacion(c['total'], previas.get(c['nombre'], 0.0)),
    } for c in _categorias_top(cid, rango, limite=20)]
    total = sum(float(f['ingreso'] or 0) for f in filas)
    for f in filas:
        f['participacion_pct'] = round(float(f['ingreso'] or 0) / total * 100, 2) if total else 0
    filas.sort(key=lambda f: -float(f['ingreso'] or 0))
    return {**data, 'categorias': filas[:top_n]}


def _costo_periodo(cid: int, desde, hasta) -> tuple[float, int, int]:
    filas = _platos(cid, desde, hasta)
    return (sum(f['costo_estimado'] for f in filas), sum(f['unidades'] for f in filas),
            sum(1 for f in filas if f['sin_costo_cargado']))


def _ganancia(cid: int, args: dict, original) -> dict:
    """Totales, descuentos y costo de productos de inventario salen de la tool original; se suma el costo de
    las recetas de los platos (que la original no ve y deja en 0)."""
    data = original(args)
    rango = resolver_rango(args)
    costo, unidades, sin_costo = _costo_periodo(cid, rango['desde'], rango['hasta'])
    costo += float(data.get('costo_estimado') or 0)
    total = float(data.get('total_ventas') or 0)
    ganancia = total - costo
    data.update({
        'unidades_vendidas': int(data.get('unidades_vendidas') or 0) + unidades,
        'costo_estimado': costo,
        'ganancia_bruta_estimada': ganancia,
        'margen_bruto_pct': round(ganancia / total * 100, 2) if total else None,
        'productos_sin_costo': int(data.get('productos_sin_costo') or 0) + sin_costo,
        'metodo_calculo': METODO,
    })
    anterior = data.get('comparacion_anterior')
    if isinstance(anterior, dict):
        costo_platos_ant = _costo_periodo(cid, rango['anterior_desde'], rango['anterior_hasta'])[0]
        costo_ant = float(anterior.get('costo_estimado') or 0) + costo_platos_ant
        total_ant = float(anterior.get('total_ventas') or 0)
        anterior.update({
            'costo_estimado': costo_ant,
            'ganancia_bruta_estimada': total_ant - costo_ant,
            'margen_bruto_pct': round((total_ant - costo_ant) / total_ant * 100, 2) if total_ant else None,
        })
    return data


_ADAPTADORES = {
    'ventas_top_productos': _top_productos,
    'ventas_rentabilidad_productos': _rentabilidad,
    'ventas_productos_bajo_margen': _bajo_margen,
    'ventas_por_categoria': _por_categoria,
    'ventas_ganancia_periodo': _ganancia,
}


def ejecutar_si_gastronomia(nombre: str, args: dict, handler, usuario=None):
    """Devuelve la data gastronomica o None si la tool no aplica o gastronomia no esta activa."""
    adaptador = _ADAPTADORES.get(nombre)
    if adaptador is None:
        return None
    cid = _cliente_id()
    if not cid:
        return None
    return adaptador(int(cid), args or {}, lambda a: handler(a, usuario=usuario))
