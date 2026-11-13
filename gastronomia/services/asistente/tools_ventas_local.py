"""Consultas de ventas propias de gastronomia para el panel del asistente.

Las tools del backoffice que rankean o calculan costo por producto (ventas_top_productos, rentabilidad,
ventas por categoria...) cruzan DetalleVenta.id_producto, pero las ventas de gastronomia guardan el plato
como servicio: para el local esas tools devuelven vacio o ganancia sin costo. Estas tools leen los reportes
de gastronomia (pedidos cobrados + recetas) y reemplazan a esas en el panel.
"""
from __future__ import annotations

from app.services.ia_backoffice.periods import resolver_rango
from app.utils.helpers import utc_bounds_for_local_dates
from gastronomia.services.ganancia_service import MAX_DIAS, ganancia_estimada
from gastronomia.services.reportes_service import productos_mas_vendidos

MAX_FILAS = 15

_PERIODO = {
    'type': 'string', 'enum': ['hoy', 'ayer', '7d', '30d', 'mes', 'trimestre', 'anio', 'custom'],
    'description': 'mes = este mes. Para otro rango (ej. el mes pasado) usa custom con desde/hasta.',
}
_FECHA = {'type': 'string', 'description': 'YYYY-MM-DD, solo con periodo custom'}


def _tool(name: str, description: str, properties: dict) -> dict:
    return {'type': 'function', 'function': {
        'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties, 'required': []},
    }}


TOOLS_VENTAS_LOCAL = [
    _tool('platos_mas_vendidos',
          'Ranking de platos del menu mas vendidos (unidades y total cobrado) en un periodo. Usala para "plato mas '
          'vendido", "que se vende mas/menos", ranking de platos. Incluye ventas importadas.',
          {'periodo': _PERIODO, 'desde': _FECHA, 'hasta': _FECHA, 'limite': {'type': 'integer'}}),
    _tool('ganancia_del_local',
          'Ganancia estimada del local en un periodo: ventas cobradas - costo de recetas de lo vendido - gastos '
          '(caja, fijos, sueldos). Trae los platos que mas dejan y los vendidos sin costo cargado. Usala para '
          'ganancia, margen o rentabilidad de platos. Maximo 93 dias.',
          {'periodo': _PERIODO, 'desde': _FECHA, 'hasta': _FECHA}),
]

# Tools del backoffice que en gastronomia darian datos vacios o engañosos (no ven los platos).
TOOLS_BACKOFFICE_REEMPLAZADAS = {
    'ventas_top_productos', 'ventas_rentabilidad_productos', 'ventas_productos_bajo_margen',
    'ventas_por_categoria', 'ventas_ganancia_periodo', 'producto_detalle_360', 'inventario_productos_inmovilizados',
}


def _rango(args: dict) -> dict:
    return resolver_rango({k: args.get(k) for k in ('periodo', 'desde', 'hasta')})


def platos_mas_vendidos(cliente_id: int, args: dict) -> dict:
    rango = _rango(args)
    inicio, fin = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    limite = max(1, min(int(args.get('limite') or 10), MAX_FILAS))
    platos = productos_mas_vendidos(cliente_id, inicio, fin, limite=limite)
    return {
        'periodo': rango['periodo_label'],
        'desde': rango['desde'].isoformat(),
        'hasta': rango['hasta'].isoformat(),
        'platos': [{'plato': p['nombre_producto'], 'unidades': p['cantidad'], 'total': p['total']} for p in platos],
    }


def ganancia_del_local(cliente_id: int, args: dict) -> dict:
    rango = _rango(args)
    if (rango['hasta'] - rango['desde']).days + 1 > MAX_DIAS:
        return {'error': f'El rango maximo es de {MAX_DIAS} dias; pedi un periodo mas corto.'}
    data = ganancia_estimada(cliente_id, rango['desde'].isoformat(), rango['hasta'].isoformat())
    return {
        'periodo': rango['periodo_label'],
        'desde': data['periodo']['desde'],
        'hasta': data['periodo']['hasta'],
        'totales': data['totales'],
        'platos_que_mas_dejan': data['platos'][:MAX_FILAS],
        'platos_vendidos_sin_costo': [p.get('nombre') for p in data['platos_sin_costo'][:MAX_FILAS]],
        'compras_del_periodo': data['compras'],
        'gastos_principales': data['gastos_detalle'][:10],
        'nota': 'Estimada: el costo sale de las recetas actuales; platos sin receta o insumos sin costo suman 0 de costo.',
    }


TOOLS_VENTAS_LOCAL_FN = {
    'platos_mas_vendidos': platos_mas_vendidos,
    'ganancia_del_local': ganancia_del_local,
}
