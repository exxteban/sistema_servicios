from sqlalchemy import func

from app import db
from app.models import Producto, RecepcionCompraUsado
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango


def _base_usados(desde, hasta):
    return RecepcionCompraUsado.query.filter(
        RecepcionCompraUsado.fecha_formulario >= desde,
        RecepcionCompraUsado.fecha_formulario <= hasta,
    )


def usados_resumen(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    base = _base_usados(rango['desde'], rango['hasta'])
    fila = base.with_entities(
        func.count(RecepcionCompraUsado.id_recepcion_compra_usado).label('cantidad'),
        func.coalesce(func.sum(RecepcionCompraUsado.monto_compra), 0).label('monto'),
    ).first()
    return {
        **rango,
        'cantidad_recepciones': int(getattr(fila, 'cantidad', 0) or 0),
        'monto_total_compra': float(getattr(fila, 'monto', 0) or 0),
        'con_producto_creado': int(base.filter(RecepcionCompraUsado.id_producto.isnot(None)).count()),
        'sin_producto_creado': int(base.filter(RecepcionCompraUsado.id_producto.is_(None)).count()),
        'con_compra_asociada': int(base.filter(RecepcionCompraUsado.id_compra.isnot(None)).count()),
    }


def usados_pendientes_revision(args: dict, usuario=None) -> dict:
    top_n = normalizar_top_n(args.get('top_n'), default=10)
    filas = (
        RecepcionCompraUsado.query
        .filter(db.or_(RecepcionCompraUsado.id_producto.is_(None), RecepcionCompraUsado.id_compra.is_(None)))
        .order_by(RecepcionCompraUsado.fecha_formulario.desc(), RecepcionCompraUsado.id_recepcion_compra_usado.desc())
        .limit(top_n)
        .all()
    )
    return {
        'pendientes': [
            {
                'id_recepcion': r.id_recepcion_compra_usado,
                'numero_formulario': r.numero_formulario_display,
                'fecha_formulario': r.fecha_formulario.isoformat() if r.fecha_formulario else None,
                'producto': r.resumen_producto,
                'vendedor': r.vendedor_nombres_apellidos,
                'monto_compra': float(r.monto_compra or 0),
                'falta_producto': r.id_producto is None,
                'falta_compra': r.id_compra is None,
            }
            for r in filas
        ],
    }


def usados_margen_estimado(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    filas = (
        db.session.query(RecepcionCompraUsado, Producto)
        .join(Producto, Producto.id_producto == RecepcionCompraUsado.id_producto)
        .filter(
            RecepcionCompraUsado.fecha_formulario >= rango['desde'],
            RecepcionCompraUsado.fecha_formulario <= rango['hasta'],
        )
        .all()
    )
    items = []
    total_costo = 0.0
    total_precio = 0.0
    for recepcion, producto in filas:
        costo = float(recepcion.monto_compra or 0)
        precio = float(producto.precio_venta or 0)
        total_costo += costo
        total_precio += precio
        items.append({
            'id_recepcion': recepcion.id_recepcion_compra_usado,
            'codigo': producto.codigo,
            'producto': producto.nombre,
            'costo_compra': costo,
            'precio_venta_actual': precio,
            'margen_estimado': precio - costo,
            'margen_pct': round(((precio - costo) / precio) * 100, 2) if precio else None,
        })
    return {
        **rango,
        'cantidad': len(items),
        'costo_total': total_costo,
        'precio_venta_total_actual': total_precio,
        'margen_estimado_total': total_precio - total_costo,
        'items': sorted(items, key=lambda item: item['margen_estimado'])[:normalizar_top_n(args.get('top_n'), default=10)],
    }


def usados_por_estado(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    base = _base_usados(rango['desde'], rango['hasta'])
    return {
        **rango,
        'por_estado_operativo': [
            {'estado': 'pendiente_producto', 'cantidad': int(base.filter(RecepcionCompraUsado.id_producto.is_(None)).count())},
            {'estado': 'pendiente_compra', 'cantidad': int(base.filter(RecepcionCompraUsado.id_compra.is_(None)).count())},
            {'estado': 'completo', 'cantidad': int(base.filter(RecepcionCompraUsado.id_producto.isnot(None), RecepcionCompraUsado.id_compra.isnot(None)).count())},
        ],
    }
