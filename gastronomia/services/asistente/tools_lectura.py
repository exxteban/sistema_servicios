"""Tools de lectura del asistente de configuracion gastronomica."""
from __future__ import annotations

from gastronomia.services.asistente import resolver
from gastronomia.services.asistente.guia_navegacion import donde_esta
from gastronomia.services.costos_service import costo_plato, resumen_costos_platos
from gastronomia.services.menu_service import listar_categorias, listar_productos
from gastronomia.services.modificadores_service import listar_grupos_producto
from gastronomia.services.salon_service import listar_mesas
from gastronomia.services.stock_service import listar_insumos, listar_resumen_recetas, obtener_receta

MAX_ITEMS = 200


def ver_menu(cliente_id: int, args: dict) -> dict:
    categorias = listar_categorias(cliente_id)
    productos = listar_productos(cliente_id)
    salida = []
    for cat in categorias:
        platos = [p for p in productos if p.categoria_id == cat.id_categoria]
        salida.append({
            'id_categoria': cat.id_categoria,
            'nombre': cat.nombre,
            'visible': bool(cat.visible),
            'platos': [
                {
                    'id_producto': p.id_producto,
                    'nombre': p.nombre,
                    'precio': float(p.precio or 0),
                    'disponible': bool(p.disponible),
                    'descripcion': (p.descripcion or '')[:120],
                }
                for p in platos[:MAX_ITEMS]
            ],
        })
    return {'categorias': salida, 'total_platos': len(productos)}


def ver_insumos(cliente_id: int, args: dict) -> dict:
    insumos = listar_insumos(cliente_id)
    return {
        'total': len(insumos),
        'insumos': [
            {
                'id_insumo': i.id_producto,
                'nombre': i.nombre,
                'unidad': i.unidad_stock or 'unidad',
                'stock_actual': int(i.stock_actual or 0),
                'stock_minimo': int(i.stock_minimo or 0),
                'precio_compra': float(i.precio_compra or 0),
            }
            for i in insumos[:MAX_ITEMS]
        ],
    }


def ver_plato(cliente_id: int, args: dict) -> dict:
    plato = resolver.plato(cliente_id, args.get('plato'))
    if not plato:
        return {'error': 'Plato no encontrado. Usa ver_menu para ver nombres e ids.'}
    receta = obtener_receta(cliente_id, plato.id_producto)
    grupos = listar_grupos_producto(cliente_id, plato.id_producto)
    return {
        'id_producto': plato.id_producto,
        'nombre': plato.nombre,
        'precio': float(plato.precio or 0),
        'receta': [
            {'insumo': item.get('insumo_nombre') or item.get('insumo_id'), 'cantidad': item.get('cantidad'),
             'unidad': item.get('unidad_stock')}
            for item in receta['items']
        ],
        'grupos_opciones': [
            {
                'nombre': g.nombre,
                'tipo': g.tipo,
                'opciones': [
                    {'nombre': o.nombre, 'precio_delta': float(o.precio_delta or 0)}
                    for o in g.opciones_ordenadas()
                ],
            }
            for g in grupos
        ],
        'costo': costo_plato(cliente_id, plato.id_producto),
    }


def estado_configuracion(cliente_id: int, args: dict) -> dict:
    """Checklist de lo que falta para arrancar el negocio."""
    categorias = listar_categorias(cliente_id)
    productos = listar_productos(cliente_id)
    insumos = listar_insumos(cliente_id)
    recetas = listar_resumen_recetas(cliente_id)
    mesas = listar_mesas(cliente_id)
    costos = resumen_costos_platos(cliente_id)
    sin_receta = [r['producto_nombre'] for r in recetas if not r['receta_activa']]
    sin_precio = [p.nombre for p in productos if not float(p.precio or 0)]
    insumos_sin_costo = [i.nombre for i in insumos if not float(i.precio_compra or 0)]
    margen_negativo = [c['producto_nombre'] for c in costos if c['tiene_costo'] and c['ganancia'] < 0]
    return {
        'categorias': len(categorias),
        'platos': len(productos),
        'insumos': len(insumos),
        'mesas': len(mesas),
        'platos_sin_precio': sin_precio[:30],
        'platos_sin_receta': sin_receta[:30],
        'insumos_sin_precio_compra': insumos_sin_costo[:30],
        'platos_con_ganancia_negativa': margen_negativo[:30],
    }


TOOLS_LECTURA = {
    'donde_esta': donde_esta,
    'ver_menu': ver_menu,
    'ver_insumos': ver_insumos,
    'ver_plato': ver_plato,
    'estado_configuracion': estado_configuracion,
}
