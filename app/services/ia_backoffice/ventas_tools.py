from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func

from app import db
from app.models import Categoria, DetalleVenta, Producto, Usuario, Venta
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local


MESES_ES = {
    1: 'Enero',
    2: 'Febrero',
    3: 'Marzo',
    4: 'Abril',
    5: 'Mayo',
    6: 'Junio',
    7: 'Julio',
    8: 'Agosto',
    9: 'Septiembre',
    10: 'Octubre',
    11: 'Noviembre',
    12: 'Diciembre',
}


def _pct(actual: float, anterior: float) -> float | None:
    if not anterior:
        return None
    return round(((actual - anterior) / anterior) * 100, 2)


def _base_ventas(desde, hasta):
    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde, hasta)
    return Venta.query.filter(
        Venta.estado == 'completada',
        Venta.fecha_venta >= inicio_utc,
        Venta.fecha_venta < fin_utc,
    )


def _resumen(desde, hasta) -> dict:
    fila = (
        _base_ventas(desde, hasta)
        .with_entities(
            func.coalesce(func.sum(Venta.total), 0).label('total'),
            func.count(Venta.id_venta).label('cantidad'),
        )
        .first()
    )
    total = float(getattr(fila, 'total', 0) or 0)
    cantidad = int(getattr(fila, 'cantidad', 0) or 0)
    return {
        'total_ventas': total,
        'cantidad_ventas': cantidad,
        'ticket_promedio': round(total / cantidad, 2) if cantidad else 0,
    }


def _rentabilidad_base(desde, hasta):
    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde, hasta)
    return (
        db.session.query(
            DetalleVenta.id_producto,
            Producto.codigo,
            Producto.nombre,
            Categoria.nombre.label('categoria'),
            func.coalesce(func.sum(DetalleVenta.cantidad), 0).label('unidades'),
            func.coalesce(func.sum(DetalleVenta.subtotal), 0).label('ingreso_items'),
            func.coalesce(func.sum(DetalleVenta.cantidad * Producto.precio_compra), 0).label('costo_estimado'),
            func.coalesce(func.sum(DetalleVenta.descuento_linea), 0).label('descuento_lineas'),
            func.min(Producto.precio_compra).label('precio_compra_min'),
        )
        .join(Producto, Producto.id_producto == DetalleVenta.id_producto)
        .join(Categoria, Categoria.id_categoria == Producto.id_categoria)
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(Venta.estado == 'completada', Venta.fecha_venta >= inicio_utc, Venta.fecha_venta < fin_utc)
        .group_by(DetalleVenta.id_producto, Producto.codigo, Producto.nombre, Categoria.nombre)
    )


def _venta_descuentos(desde, hasta) -> dict:
    fila = (
        _base_ventas(desde, hasta)
        .with_entities(
            func.coalesce(func.sum(Venta.subtotal), 0).label('subtotal'),
            func.coalesce(func.sum(Venta.descuento_monto), 0).label('descuento_monto'),
            func.coalesce(func.sum(Venta.total), 0).label('total'),
            func.count(Venta.id_venta).label('cantidad'),
        )
        .first()
    )
    subtotal = float(getattr(fila, 'subtotal', 0) or 0)
    descuento = float(getattr(fila, 'descuento_monto', 0) or 0)
    total = float(getattr(fila, 'total', 0) or 0)
    return {
        'subtotal_ventas': subtotal,
        'descuento_ventas': descuento,
        'total_ventas': total,
        'cantidad_ventas': int(getattr(fila, 'cantidad', 0) or 0),
        'descuento_ventas_pct': round((descuento / subtotal) * 100, 2) if subtotal else 0,
    }


def _margen(ganancia: float, ingreso: float) -> float | None:
    if not ingreso:
        return None
    return round((ganancia / ingreso) * 100, 2)


def ventas_resumen_periodo(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    actual = _resumen(rango['desde'], rango['hasta'])
    anterior = _resumen(rango['anterior_desde'], rango['anterior_hasta'])
    actual['variacion_vs_anterior_pct'] = _pct(actual['total_ventas'], anterior['total_ventas'])
    return {'periodo_label': rango['periodo_label'], **actual, 'comparacion_anterior': anterior}


def ventas_ganancia_periodo(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    resumen = _resumen(rango['desde'], rango['hasta'])
    descuentos = _venta_descuentos(rango['desde'], rango['hasta'])
    filas = _rentabilidad_base(rango['desde'], rango['hasta']).all()
    costo_estimado = sum(float(row.costo_estimado or 0) for row in filas)
    ingreso_items = sum(float(row.ingreso_items or 0) for row in filas)
    descuento_lineas = sum(float(row.descuento_lineas or 0) for row in filas)
    unidades = sum(int(row.unidades or 0) for row in filas)
    productos_sin_costo = sum(1 for row in filas if float(row.precio_compra_min or 0) <= 0)
    ganancia_bruta = float(resumen['total_ventas'] or 0) - costo_estimado
    anterior = ventas_ganancia_basica(rango['anterior_desde'], rango['anterior_hasta'])
    return {
        'periodo_label': rango['periodo_label'],
        **resumen,
        'unidades_vendidas': unidades,
        'ingreso_items': ingreso_items,
        'costo_estimado': costo_estimado,
        'ganancia_bruta_estimada': ganancia_bruta,
        'margen_bruto_pct': _margen(ganancia_bruta, resumen['total_ventas']),
        'descuento_ventas': descuentos['descuento_ventas'],
        'descuento_lineas': descuento_lineas,
        'descuento_total_estimado': descuentos['descuento_ventas'] + descuento_lineas,
        'productos_sin_costo': productos_sin_costo,
        'comparacion_anterior': anterior,
        'metodo_calculo': 'Ganancia estimada = total vendido - costo estimado con precio_compra actual.',
    }


def ventas_ganancia_basica(desde, hasta) -> dict:
    resumen = _resumen(desde, hasta)
    costo = sum(float(row.costo_estimado or 0) for row in _rentabilidad_base(desde, hasta).all())
    ganancia = float(resumen['total_ventas'] or 0) - costo
    return {
        'total_ventas': resumen['total_ventas'],
        'costo_estimado': costo,
        'ganancia_bruta_estimada': ganancia,
        'margen_bruto_pct': _margen(ganancia, resumen['total_ventas']),
    }


def ventas_top_productos(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    filas = (
        db.session.query(
            Producto.id_producto,
            Producto.codigo,
            Producto.nombre,
            func.coalesce(func.sum(DetalleVenta.cantidad), 0).label('unidades'),
            func.coalesce(func.sum(DetalleVenta.subtotal), 0).label('ingreso'),
        )
        .join(DetalleVenta, DetalleVenta.id_producto == Producto.id_producto)
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(Venta.estado == 'completada', Venta.fecha_venta >= inicio_utc, Venta.fecha_venta < fin_utc)
        .group_by(Producto.id_producto, Producto.codigo, Producto.nombre)
        .order_by(func.sum(DetalleVenta.subtotal).desc(), Producto.nombre.asc())
        .limit(top_n)
        .all()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'top_n': top_n,
        'productos': [
            {
                'id_producto': row.id_producto,
                'codigo': row.codigo,
                'nombre': row.nombre,
                'unidades': int(row.unidades or 0),
                'ingreso': float(row.ingreso or 0),
            }
            for row in filas
        ],
    }


def ventas_rentabilidad_productos(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    filas = (
        _rentabilidad_base(rango['desde'], rango['hasta'])
        .order_by((func.sum(DetalleVenta.subtotal) - func.sum(DetalleVenta.cantidad * Producto.precio_compra)).desc())
        .limit(top_n)
        .all()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'top_n': top_n,
        'productos': [_rentabilidad_producto_row(row) for row in filas],
        'metodo_calculo': 'Rentabilidad estimada con precio_compra actual del producto.',
    }


def ventas_productos_bajo_margen(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    productos = [_rentabilidad_producto_row(row) for row in _rentabilidad_base(rango['desde'], rango['hasta']).all()]
    productos = [item for item in productos if item['ingreso'] > 0]
    productos.sort(key=lambda item: (item['margen_pct'] if item['margen_pct'] is not None else 999, -item['ingreso']))
    return {
        'periodo_label': rango['periodo_label'],
        'top_n': top_n,
        'productos': productos[:top_n],
        'metodo_calculo': 'Margen estimado = ganancia estimada / ingreso del producto.',
    }


def _rentabilidad_producto_row(row) -> dict:
    ingreso = float(row.ingreso_items or 0)
    costo = float(row.costo_estimado or 0)
    ganancia = ingreso - costo
    return {
        'id_producto': row.id_producto,
        'codigo': row.codigo,
        'nombre': row.nombre,
        'categoria': row.categoria or 'Sin categoria',
        'unidades': int(row.unidades or 0),
        'ingreso': ingreso,
        'costo_estimado': costo,
        'ganancia_estimada': ganancia,
        'margen_pct': _margen(ganancia, ingreso),
        'descuento_lineas': float(row.descuento_lineas or 0),
        'sin_costo_cargado': float(row.precio_compra_min or 0) <= 0,
    }


def ventas_descuentos_periodo(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    descuentos = _venta_descuentos(rango['desde'], rango['hasta'])
    descuento_lineas = sum(float(row.descuento_lineas or 0) for row in _rentabilidad_base(rango['desde'], rango['hasta']).all())
    total_descuentos = descuentos['descuento_ventas'] + descuento_lineas
    base_descuento = descuentos['subtotal_ventas'] + descuento_lineas
    return {
        'periodo_label': rango['periodo_label'],
        **descuentos,
        'descuento_lineas': descuento_lineas,
        'descuento_total_estimado': total_descuentos,
        'descuento_total_pct': round((total_descuentos / base_descuento) * 100, 2) if base_descuento else 0,
    }


def ventas_por_categoria(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    actual = _categorias(rango['desde'], rango['hasta'])
    anterior = {item['categoria']: item for item in _categorias(rango['anterior_desde'], rango['anterior_hasta'])}
    total = sum(item['ingreso'] for item in actual)
    categorias = []
    for item in actual[:top_n]:
        previo = anterior.get(item['categoria'], {})
        categorias.append({
            **item,
            'participacion_pct': round((item['ingreso'] / total) * 100, 2) if total else 0,
            'variacion_vs_anterior_pct': _pct(item['ingreso'], float(previo.get('ingreso') or 0)),
        })
    return {'periodo_label': rango['periodo_label'], 'categorias': categorias}


def _categorias(desde, hasta) -> list[dict]:
    inicio_utc, fin_utc = utc_bounds_for_local_dates(desde, hasta)
    filas = (
        db.session.query(
            Categoria.nombre.label('categoria'),
            func.coalesce(func.sum(DetalleVenta.cantidad), 0).label('unidades'),
            func.coalesce(func.sum(DetalleVenta.subtotal), 0).label('ingreso'),
        )
        .join(Producto, Producto.id_categoria == Categoria.id_categoria)
        .join(DetalleVenta, DetalleVenta.id_producto == Producto.id_producto)
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(Venta.estado == 'completada', Venta.fecha_venta >= inicio_utc, Venta.fecha_venta < fin_utc)
        .group_by(Categoria.id_categoria, Categoria.nombre)
        .order_by(func.sum(DetalleVenta.subtotal).desc(), Categoria.nombre.asc())
        .all()
    )
    return [
        {'categoria': row.categoria or 'Sin categoria', 'unidades': int(row.unidades or 0), 'ingreso': float(row.ingreso or 0)}
        for row in filas
    ]


def ventas_tendencia(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    ventas = db.session.query(Venta.fecha_venta, Venta.total).filter(
        Venta.estado == 'completada',
        Venta.fecha_venta >= inicio_utc,
        Venta.fecha_venta < fin_utc,
    ).all()
    por_dia = defaultdict(lambda: {'total_ventas': 0.0, 'cantidad_ventas': 0})
    for venta in ventas:
        local_dt = utc_naive_to_local(venta.fecha_venta)
        if not local_dt:
            continue
        item = por_dia[local_dt.date()]
        item['total_ventas'] += float(venta.total or 0)
        item['cantidad_ventas'] += 1
    serie = []
    cursor = rango['desde']
    while cursor <= rango['hasta']:
        item = por_dia.get(cursor, {'total_ventas': 0.0, 'cantidad_ventas': 0})
        serie.append({'fecha': cursor.isoformat(), **item})
        cursor += timedelta(days=1)
    return {'periodo_label': rango['periodo_label'], 'granularidad': 'dia', 'serie': serie}


def ventas_ranking_mensual(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango((args or {}) if args else {'periodo': 'anio'})
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    ventas = db.session.query(Venta.fecha_venta, Venta.total).filter(
        Venta.estado == 'completada',
        Venta.fecha_venta >= inicio_utc,
        Venta.fecha_venta < fin_utc,
    ).all()
    por_mes = {}
    for venta in ventas:
        local_dt = utc_naive_to_local(venta.fecha_venta)
        if not local_dt:
            continue
        clave = (local_dt.year, local_dt.month)
        item = por_mes.setdefault(clave, {
            'anio': local_dt.year,
            'mes_numero': local_dt.month,
            'mes_nombre': MESES_ES.get(local_dt.month, str(local_dt.month)),
            'total_ventas': 0.0,
            'cantidad_ventas': 0,
        })
        item['total_ventas'] += float(venta.total or 0)
        item['cantidad_ventas'] += 1

    meses_cronologicos = []
    cursor_anio = rango['desde'].year
    cursor_mes = rango['desde'].month
    while (cursor_anio, cursor_mes) <= (rango['hasta'].year, rango['hasta'].month):
        meses_cronologicos.append(
            por_mes.get((cursor_anio, cursor_mes), {
                'anio': cursor_anio,
                'mes_numero': cursor_mes,
                'mes_nombre': MESES_ES.get(cursor_mes, str(cursor_mes)),
                'total_ventas': 0.0,
                'cantidad_ventas': 0,
            })
        )
        if cursor_mes == 12:
            cursor_anio += 1
            cursor_mes = 1
        else:
            cursor_mes += 1
    ranking = sorted(
        meses_cronologicos,
        key=lambda item: (-item['total_ventas'], -item['cantidad_ventas'], item['anio'], item['mes_numero']),
    )
    for indice, item in enumerate(ranking, start=1):
        item['ranking'] = indice

    mejor_mes = ranking[0] if ranking else None
    segundo_mes = ranking[1] if len(ranking) > 1 else None
    return {
        'periodo_label': rango['periodo_label'],
        'desde': rango['desde'].isoformat(),
        'hasta': rango['hasta'].isoformat(),
        'anio_consultado': rango['hasta'].year if rango['desde'].year == rango['hasta'].year else None,
        'mejor_mes': mejor_mes,
        'segundo_mes': segundo_mes,
        'ranking_meses': ranking,
        'detalle_cronologico': meses_cronologicos,
    }


def ventas_por_vendedor(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    filas = (
        db.session.query(
            Venta.id_usuario_vendedor,
            Usuario.username,
            Usuario.nombre_completo,
            func.count(Venta.id_venta).label('cantidad_ventas'),
            func.coalesce(func.sum(Venta.total), 0).label('total_ventas'),
        )
        .outerjoin(Usuario, Usuario.id_usuario == Venta.id_usuario_vendedor)
        .filter(Venta.estado == 'completada', Venta.fecha_venta >= inicio_utc, Venta.fecha_venta < fin_utc)
        .group_by(Venta.id_usuario_vendedor, Usuario.username, Usuario.nombre_completo)
        .order_by(func.sum(Venta.total).desc())
        .limit(top_n)
        .all()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'vendedores': [
            {
                'id_usuario': row.id_usuario_vendedor,
                'username': row.username or 'sin_vendedor',
                'nombre': row.nombre_completo or 'Sin vendedor asignado',
                'cantidad_ventas': int(row.cantidad_ventas or 0),
                'total_ventas': float(row.total_ventas or 0),
            }
            for row in filas
        ],
    }
