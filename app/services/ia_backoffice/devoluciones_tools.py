from sqlalchemy import func

from app import db
from app.models import DetalleDevolucion, Devolucion, Producto
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.utils.helpers import utc_bounds_for_local_dates


def _base_devoluciones(desde, hasta):
    inicio, fin = utc_bounds_for_local_dates(desde, hasta)
    return Devolucion.query.filter(
        Devolucion.estado != 'anulada',
        Devolucion.fecha_devolucion >= inicio,
        Devolucion.fecha_devolucion < fin,
    )


def devoluciones_resumen(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    base = _base_devoluciones(rango['desde'], rango['hasta'])
    fila = base.with_entities(
        func.count(Devolucion.id_devolucion).label('cantidad'),
        func.coalesce(func.sum(Devolucion.monto_total), 0).label('monto_total'),
    ).first()
    por_accion = [
        {'accion_stock': row.accion_stock or 'sin_accion', 'cantidad': int(row.cantidad or 0), 'monto': float(row.monto or 0)}
        for row in base.with_entities(
            Devolucion.accion_stock,
            func.count(Devolucion.id_devolucion).label('cantidad'),
            func.coalesce(func.sum(Devolucion.monto_total), 0).label('monto'),
        ).group_by(Devolucion.accion_stock).all()
    ]
    return {
        **rango,
        'cantidad_devoluciones': int(getattr(fila, 'cantidad', 0) or 0),
        'monto_total_devuelto': float(getattr(fila, 'monto_total', 0) or 0),
        'por_accion_stock': por_accion,
    }


def productos_mas_devueltos(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n(args.get('top_n'), default=10)
    inicio, fin = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    filas = (
        db.session.query(
            Producto.id_producto,
            Producto.codigo,
            Producto.nombre,
            func.coalesce(func.sum(DetalleDevolucion.cantidad), 0).label('unidades'),
            func.coalesce(func.sum(DetalleDevolucion.subtotal), 0).label('monto'),
        )
        .join(DetalleDevolucion, DetalleDevolucion.id_producto == Producto.id_producto)
        .join(Devolucion, Devolucion.id_devolucion == DetalleDevolucion.id_devolucion)
        .filter(Devolucion.estado != 'anulada', Devolucion.fecha_devolucion >= inicio, Devolucion.fecha_devolucion < fin)
        .group_by(Producto.id_producto, Producto.codigo, Producto.nombre)
        .order_by(func.coalesce(func.sum(DetalleDevolucion.cantidad), 0).desc())
        .limit(top_n)
        .all()
    )
    return {
        **rango,
        'productos': [
            {
                'id_producto': row.id_producto,
                'codigo': row.codigo,
                'nombre': row.nombre,
                'unidades_devueltas': int(row.unidades or 0),
                'monto_devuelto': float(row.monto or 0),
            }
            for row in filas
        ],
    }


def motivos_de_devolucion(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n(args.get('top_n'), default=10)
    filas = (
        _base_devoluciones(rango['desde'], rango['hasta'])
        .with_entities(
            Devolucion.motivo,
            func.count(Devolucion.id_devolucion).label('cantidad'),
            func.coalesce(func.sum(Devolucion.monto_total), 0).label('monto'),
        )
        .group_by(Devolucion.motivo)
        .order_by(func.count(Devolucion.id_devolucion).desc())
        .limit(top_n)
        .all()
    )
    return {
        **rango,
        'motivos': [
            {'motivo': row.motivo or 'Sin motivo', 'cantidad': int(row.cantidad or 0), 'monto': float(row.monto or 0)}
            for row in filas
        ],
    }
