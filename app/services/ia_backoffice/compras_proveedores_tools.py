from sqlalchemy import func

from app import db
from app.models import Compra, CuentaPorPagar, DetalleCompra, Producto, Proveedor
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango


def _base_compras(desde, hasta):
    return Compra.query.filter(
        Compra.estado != 'anulada',
        Compra.fecha_compra >= desde,
        Compra.fecha_compra <= hasta,
    )


def compras_resumen_periodo(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n(args.get('top_n'), default=5)
    base = _base_compras(rango['desde'], rango['hasta'])
    fila = base.with_entities(
        func.coalesce(func.sum(Compra.total), 0).label('total'),
        func.count(Compra.id_compra).label('cantidad'),
        func.coalesce(func.sum(func.coalesce(Compra.total_iva_10, 0) + func.coalesce(Compra.total_iva_5, 0)), 0).label('iva'),
    ).first()
    por_estado = [
        {'estado': row.estado or 'sin_estado', 'cantidad': int(row.cantidad or 0), 'total': float(row.total or 0)}
        for row in base.with_entities(
            Compra.estado,
            func.count(Compra.id_compra).label('cantidad'),
            func.coalesce(func.sum(Compra.total), 0).label('total'),
        ).group_by(Compra.estado).all()
    ]
    productos = (
        db.session.query(
            Producto.codigo,
            Producto.nombre,
            func.coalesce(func.sum(DetalleCompra.cantidad), 0).label('unidades'),
            func.coalesce(func.sum(DetalleCompra.subtotal), 0).label('total_comprado'),
        )
        .join(DetalleCompra, DetalleCompra.id_producto == Producto.id_producto)
        .join(Compra, Compra.id_compra == DetalleCompra.id_compra)
        .filter(Compra.estado != 'anulada', Compra.fecha_compra >= rango['desde'], Compra.fecha_compra <= rango['hasta'])
        .group_by(Producto.codigo, Producto.nombre)
        .order_by(func.coalesce(func.sum(DetalleCompra.subtotal), 0).desc())
        .limit(top_n)
        .all()
    )
    return {
        **rango,
        'total_compras': float(getattr(fila, 'total', 0) or 0),
        'cantidad_compras': int(getattr(fila, 'cantidad', 0) or 0),
        'iva_compras': float(getattr(fila, 'iva', 0) or 0),
        'ticket_promedio_compra': round(float(getattr(fila, 'total', 0) or 0) / int(getattr(fila, 'cantidad', 0) or 1), 2) if getattr(fila, 'cantidad', 0) else 0,
        'por_estado': por_estado,
        'productos_mas_comprados': [
            {
                'codigo': row.codigo,
                'nombre': row.nombre,
                'unidades': int(row.unidades or 0),
                'total_comprado': float(row.total_comprado or 0),
            }
            for row in productos
        ],
    }


def proveedores_top(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n(args.get('top_n'), default=10)
    filas = (
        db.session.query(
            Proveedor.id_proveedor,
            Proveedor.nombre,
            Proveedor.ruc,
            func.count(Compra.id_compra).label('cantidad_compras'),
            func.coalesce(func.sum(Compra.total), 0).label('total_comprado'),
            func.max(Compra.fecha_compra).label('ultima_compra'),
            func.coalesce(func.sum(CuentaPorPagar.saldo_pendiente), 0).label('saldo_pendiente'),
        )
        .join(Compra, Compra.id_proveedor == Proveedor.id_proveedor)
        .outerjoin(CuentaPorPagar, CuentaPorPagar.id_compra == Compra.id_compra)
        .filter(Compra.estado != 'anulada', Compra.fecha_compra >= rango['desde'], Compra.fecha_compra <= rango['hasta'])
        .group_by(Proveedor.id_proveedor, Proveedor.nombre, Proveedor.ruc)
        .order_by(func.coalesce(func.sum(Compra.total), 0).desc())
        .limit(top_n)
        .all()
    )
    return {
        **rango,
        'proveedores': [
            {
                'id_proveedor': row.id_proveedor,
                'nombre': row.nombre,
                'ruc': row.ruc,
                'cantidad_compras': int(row.cantidad_compras or 0),
                'total_comprado': float(row.total_comprado or 0),
                'saldo_pendiente': float(row.saldo_pendiente or 0),
                'ultima_compra': row.ultima_compra.isoformat() if row.ultima_compra else None,
            }
            for row in filas
        ],
    }


def proveedor_detalle_360(args: dict, usuario=None) -> dict:
    proveedor = None
    if args.get('id_proveedor'):
        proveedor = db.session.get(Proveedor, int(args.get('id_proveedor') or 0))
    busqueda = (args.get('busqueda') or args.get('referencia') or '').strip()
    if proveedor is None and busqueda:
        patron = f'%{busqueda}%'
        candidatos = Proveedor.query.filter(
            db.or_(Proveedor.nombre.ilike(patron), Proveedor.ruc.ilike(patron), Proveedor.telefono.ilike(patron))
        ).limit(6).all()
        if len(candidatos) != 1:
            return {
                'encontrado': False,
                'requiere_seleccion': bool(candidatos),
                'candidatos': [
                    {'id_proveedor': p.id_proveedor, 'nombre': p.nombre, 'ruc': p.ruc, 'telefono': p.telefono}
                    for p in candidatos
                ],
                'error': 'proveedor_no_encontrado' if not candidatos else 'proveedor_ambiguo',
            }
        proveedor = candidatos[0]
    if proveedor is None:
        return {'encontrado': False, 'error': 'proveedor_no_encontrado'}

    compras = Compra.query.filter_by(id_proveedor=proveedor.id_proveedor).filter(Compra.estado != 'anulada')
    total_comprado = compras.with_entities(func.coalesce(func.sum(Compra.total), 0)).scalar() or 0
    cuentas = CuentaPorPagar.query.filter_by(id_proveedor=proveedor.id_proveedor)
    saldo = cuentas.with_entities(func.coalesce(func.sum(CuentaPorPagar.saldo_pendiente), 0)).scalar() or 0
    ultima = compras.order_by(Compra.fecha_compra.desc(), Compra.id_compra.desc()).first()
    productos = Producto.query.filter_by(id_proveedor_principal=proveedor.id_proveedor).limit(10).all()
    return {
        'encontrado': True,
        'proveedor': {
            'id_proveedor': proveedor.id_proveedor,
            'nombre': proveedor.nombre,
            'ruc': proveedor.ruc,
            'telefono': proveedor.telefono,
            'email': proveedor.email,
            'dias_credito': proveedor.dias_credito,
            'activo': bool(proveedor.activo),
        },
        'total_comprado_historico': float(total_comprado),
        'saldo_pendiente': float(saldo),
        'ultima_compra': {
            'id_compra': ultima.id_compra,
            'fecha_compra': ultima.fecha_compra.isoformat() if ultima.fecha_compra else None,
            'total': float(ultima.total or 0),
            'numero_factura': ultima.numero_factura,
        } if ultima else None,
        'productos_asociados': [
            {'id_producto': p.id_producto, 'codigo': p.codigo, 'nombre': p.nombre, 'stock_actual': p.stock_actual}
            for p in productos
        ],
    }
