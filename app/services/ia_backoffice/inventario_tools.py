from sqlalchemy import func, or_

from app import db
from app.models import Categoria, DetalleVenta, Producto, Venta
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local


def inventario_resumen(args: dict | None = None, usuario=None) -> dict:
    activos = Producto.query.filter(Producto.activo.is_(True), Producto.es_servicio.is_(False))
    stock_bajo = activos.filter(Producto.stock_actual <= Producto.stock_minimo).count()
    sin_stock = activos.filter(Producto.stock_actual <= 0).count()
    valor_stock = (
        activos.with_entities(func.coalesce(func.sum(Producto.stock_actual * Producto.precio_compra), 0)).scalar()
        or 0
    )
    return {
        'productos_activos': int(activos.count()),
        'productos_stock_bajo': int(stock_bajo),
        'productos_sin_stock': int(sin_stock),
        'valor_stock_costo': float(valor_stock or 0),
    }


def inventario_productos_reponer(args: dict | None = None, usuario=None) -> dict:
    top_n = normalizar_top_n((args or {}).get('top_n'))
    filas = (
        Producto.query
        .join(Categoria, Categoria.id_categoria == Producto.id_categoria)
        .filter(
            Producto.activo.is_(True),
            Producto.es_servicio.is_(False),
            Producto.stock_actual <= Producto.stock_minimo,
        )
        .with_entities(
            Producto.id_producto,
            Producto.codigo,
            Producto.nombre,
            Categoria.nombre.label('categoria'),
            Producto.stock_actual,
            Producto.stock_minimo,
        )
        .order_by((Producto.stock_actual - Producto.stock_minimo).asc(), Producto.nombre.asc())
        .limit(top_n)
        .all()
    )
    return {
        'top_n': top_n,
        'productos': [
            {
                'id_producto': row.id_producto,
                'codigo': row.codigo,
                'nombre': row.nombre,
                'categoria': row.categoria,
                'stock_actual': int(row.stock_actual or 0),
                'stock_minimo': int(row.stock_minimo or 0),
                'unidades_sugeridas': max(int(row.stock_minimo or 0) - int(row.stock_actual or 0), 0),
            }
            for row in filas
        ],
    }


def inventario_productos_inmovilizados(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    vendidos_subq = (
        db.session.query(DetalleVenta.id_producto.label('id_producto'))
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .group_by(DetalleVenta.id_producto)
        .subquery()
    )
    filas = (
        Producto.query
        .join(Categoria, Categoria.id_categoria == Producto.id_categoria)
        .outerjoin(vendidos_subq, vendidos_subq.c.id_producto == Producto.id_producto)
        .filter(
            Producto.activo.is_(True),
            Producto.es_servicio.is_(False),
            Producto.stock_actual > 0,
            vendidos_subq.c.id_producto.is_(None),
        )
        .with_entities(
            Producto.id_producto,
            Producto.codigo,
            Producto.nombre,
            Categoria.nombre.label('categoria'),
            Producto.stock_actual,
            Producto.precio_compra,
        )
        .order_by((Producto.stock_actual * Producto.precio_compra).desc(), Producto.nombre.asc())
        .limit(top_n)
        .all()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'productos': [
            {
                'id_producto': row.id_producto,
                'codigo': row.codigo,
                'nombre': row.nombre,
                'categoria': row.categoria,
                'stock_actual': int(row.stock_actual or 0),
                'valor_stock_costo': float((row.stock_actual or 0) * (row.precio_compra or 0)),
            }
            for row in filas
        ],
    }


def _clasificar_baja_rotacion(row, unidades_periodo: int) -> str | None:
    stock = int(row.stock_actual or 0)
    stock_minimo = int(row.stock_minimo or 0)
    stock_maximo = int(row.stock_maximo or 0) if row.stock_maximo is not None else 0
    if unidades_periodo <= 0:
        return 'producto_muerto'
    if stock_maximo > 0 and stock > stock_maximo:
        return 'exceso_stock'
    if stock >= max(unidades_periodo * 4, stock_minimo * 2, 5):
        return 'exceso_stock'
    if unidades_periodo <= 2 and stock >= 3:
        return 'producto_lento'
    return None


def _accion_baja_rotacion(clasificacion: str) -> str:
    acciones = {
        'producto_muerto': 'Ofertar o rematar para liberar capital inmovilizado.',
        'producto_lento': 'Probar descuento moderado o combo con productos de alta rotacion.',
        'exceso_stock': 'Bajar reposicion y liquidar excedente con promo por tiempo limitado.',
    }
    return acciones.get(clasificacion, 'Revisar precio, visibilidad y politica de reposicion.')


def inventario_productos_baja_rotacion(args: dict | None = None, usuario=None) -> dict:
    base_args = dict(args or {})
    if not base_args.get('periodo'):
        base_args['periodo'] = '30d'
    rango = resolver_rango(base_args)
    top_n = normalizar_top_n(base_args.get('top_n'))
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    ventas_periodo_subq = (
        db.session.query(
            DetalleVenta.id_producto.label('id_producto'),
            func.coalesce(func.sum(DetalleVenta.cantidad), 0).label('unidades_periodo'),
        )
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .group_by(DetalleVenta.id_producto)
        .subquery()
    )
    ultima_venta_subq = (
        db.session.query(
            DetalleVenta.id_producto.label('id_producto'),
            func.max(Venta.fecha_venta).label('ultima_venta'),
        )
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(Venta.estado == 'completada')
        .group_by(DetalleVenta.id_producto)
        .subquery()
    )
    filas = (
        Producto.query
        .join(Categoria, Categoria.id_categoria == Producto.id_categoria)
        .outerjoin(ventas_periodo_subq, ventas_periodo_subq.c.id_producto == Producto.id_producto)
        .outerjoin(ultima_venta_subq, ultima_venta_subq.c.id_producto == Producto.id_producto)
        .filter(
            Producto.activo.is_(True),
            Producto.es_servicio.is_(False),
            Producto.stock_actual > 0,
            or_(
                func.coalesce(ventas_periodo_subq.c.unidades_periodo, 0) <= 2,
                Producto.stock_actual >= (Producto.stock_minimo * 2),
                Producto.stock_actual > Producto.stock_maximo,
            ),
        )
        .with_entities(
            Producto.id_producto,
            Producto.codigo,
            Producto.nombre,
            Categoria.nombre.label('categoria'),
            Producto.stock_actual,
            Producto.stock_minimo,
            Producto.stock_maximo,
            Producto.precio_compra,
            ventas_periodo_subq.c.unidades_periodo,
            ultima_venta_subq.c.ultima_venta,
        )
        .all()
    )
    productos = []
    for row in filas:
        unidades = int(row.unidades_periodo or 0)
        clasificacion = _clasificar_baja_rotacion(row, unidades)
        if not clasificacion:
            continue
        ultima_local = utc_naive_to_local(row.ultima_venta) if row.ultima_venta else None
        stock = int(row.stock_actual or 0)
        productos.append({
            'id_producto': row.id_producto,
            'codigo': row.codigo,
            'nombre': row.nombre,
            'categoria': row.categoria,
            'stock_actual': stock,
            'stock_minimo': int(row.stock_minimo or 0),
            'stock_maximo': int(row.stock_maximo or 0) if row.stock_maximo is not None else None,
            'unidades_periodo': unidades,
            'valor_stock_costo': float(stock * float(row.precio_compra or 0)),
            'ultima_venta': ultima_local.date().isoformat() if ultima_local else None,
            'clasificacion': clasificacion,
            'accion_recomendada': _accion_baja_rotacion(clasificacion),
        })
    productos.sort(key=lambda item: (item['clasificacion'] != 'producto_muerto', -item['valor_stock_costo'], item['nombre']))
    return {
        'periodo_label': rango['periodo_label'],
        'top_n': top_n,
        'productos': productos[:top_n],
        'criterio': 'Productos activos con stock, pocas o cero ventas en el periodo, priorizados por capital inmovilizado.',
    }
