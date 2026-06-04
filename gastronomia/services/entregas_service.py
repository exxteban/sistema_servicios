"""Consulta y resumen de entregas gastronomicas."""
from __future__ import annotations

import re
from math import ceil

from app import db
from app.utils.helpers import parse_iso_date, today_local, utc_bounds_for_local_dates, utc_naive_to_local
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem, GastronomiaPedidoPago
from gastronomia.services.pedido_service import ESTADOS_PEDIDO, serializar_pedidos


TIPOS_PEDIDO = {'mesa', 'mostrador', 'retiro', 'delivery'}
PEDIDOS_POR_PAGINA = 8


def buscar_entregas(cliente_id: int, filtros: dict) -> dict:
    fecha = _fecha_filtro(cliente_id, filtros.get('fecha'))
    inicio, fin = utc_bounds_for_local_dates(fecha, fecha)
    query = (
        GastronomiaPedido.query
        .outerjoin(
            GastronomiaPedidoPago,
            db.and_(
                GastronomiaPedidoPago.pedido_id == GastronomiaPedido.id_pedido,
                GastronomiaPedidoPago.cliente_id == GastronomiaPedido.cliente_id,
            ),
        )
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            db.or_(
                db.and_(
                    GastronomiaPedido.fecha_entrega.isnot(None),
                    GastronomiaPedido.fecha_entrega >= inicio,
                    GastronomiaPedido.fecha_entrega < fin,
                ),
                db.and_(
                    GastronomiaPedido.fecha_entrega.is_(None),
                    GastronomiaPedido.estado == 'cobrado',
                    GastronomiaPedidoPago.fecha_pago >= inicio,
                    GastronomiaPedidoPago.fecha_pago < fin,
                ),
            ),
        )
    )

    estado = (filtros.get('estado') or '').strip().lower()
    if estado in ESTADOS_PEDIDO:
        query = query.filter(GastronomiaPedido.estado == estado)
    else:
        query = query.filter(GastronomiaPedido.estado != 'cancelado')

    tipo_pedido = (filtros.get('tipo_pedido') or '').strip().lower()
    if tipo_pedido in TIPOS_PEDIDO:
        query = query.filter(GastronomiaPedido.tipo_pedido == tipo_pedido)

    pagado = _parse_paid_filter(filtros.get('pagado'))
    if pagado is True:
        query = query.filter(GastronomiaPedidoPago.id_pago.isnot(None))
    elif pagado is False:
        query = query.filter(GastronomiaPedidoPago.id_pago.is_(None))

    query = _apply_search(query, filtros.get('q'))
    total = query.with_entities(GastronomiaPedido.id_pedido).distinct().count()
    por_pagina = min(_parse_positive_int(filtros.get('per_page'), PEDIDOS_POR_PAGINA), 50)
    paginas = max(1, ceil(total / por_pagina)) if total else 1
    pagina = min(_parse_positive_int(filtros.get('page'), 1), paginas)
    fecha_operativa = db.func.coalesce(GastronomiaPedido.fecha_entrega, GastronomiaPedidoPago.fecha_pago)
    pagina_rows = (
        query
        .with_entities(
            GastronomiaPedido.id_pedido,
            db.func.max(fecha_operativa).label('fecha_operativa'),
        )
        .group_by(GastronomiaPedido.id_pedido)
        .order_by(db.func.max(fecha_operativa).desc(), GastronomiaPedido.id_pedido.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )
    pedido_ids = [int(row.id_pedido) for row in pagina_rows]
    pedidos_por_id = {
        int(pedido.id_pedido): pedido
        for pedido in GastronomiaPedido.query.filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.id_pedido.in_(pedido_ids),
        ).all()
    }
    pedidos = [pedidos_por_id[pedido_id] for pedido_id in pedido_ids if pedido_id in pedidos_por_id]
    pedidos_data = _serializar_pedidos_entregas(pedidos)
    return {
        'fecha': fecha.isoformat(),
        'resumen': _resumen(query),
        'pedidos': pedidos_data,
        'paginacion': {
            'pagina': pagina,
            'por_pagina': por_pagina,
            'total': total,
            'paginas': paginas,
            'tiene_anterior': pagina > 1,
            'tiene_siguiente': pagina < paginas,
        },
    }


def _fecha_filtro(cliente_id: int, value) -> object:
    text = str(value or '').strip().lower()
    if text in {'hoy', 'today'}:
        return today_local()
    if text:
        return parse_iso_date(text) or today_local()
    return _ultima_fecha_entrega(cliente_id) or today_local()


def _ultima_fecha_entrega(cliente_id: int):
    ultima_entrega = (
        db.session.query(db.func.max(GastronomiaPedido.fecha_entrega))
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.fecha_entrega.isnot(None),
        )
        .scalar()
    )
    ultimo_cobro = (
        db.session.query(db.func.max(GastronomiaPedidoPago.fecha_pago))
        .join(
            GastronomiaPedido,
            db.and_(
                GastronomiaPedido.id_pedido == GastronomiaPedidoPago.pedido_id,
                GastronomiaPedido.cliente_id == GastronomiaPedidoPago.cliente_id,
            ),
        )
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.estado == 'cobrado',
            GastronomiaPedido.fecha_entrega.is_(None),
        )
        .scalar()
    )
    ultima_fecha = max([fecha for fecha in (ultima_entrega, ultimo_cobro) if fecha], default=None)
    local = utc_naive_to_local(ultima_fecha)
    return local.date() if local else None


def _parse_paid_filter(value) -> bool | None:
    text = str(value or '').strip().lower()
    if text in {'1', 'true', 'si', 'sí', 'pagado'}:
        return True
    if text in {'0', 'false', 'no', 'pendiente'}:
        return False
    return None


def _parse_positive_int(value, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _apply_search(query, value):
    text = str(value or '').strip()
    if not text:
        return query
    like = f'%{text}%'
    conditions = [
        GastronomiaPedido.mesa.ilike(like),
        GastronomiaPedido.referencia_entrega.ilike(like),
        GastronomiaPedido.nombre_cliente.ilike(like),
        GastronomiaPedido.celular_cliente.ilike(like),
        GastronomiaPedido.direccion_entrega.ilike(like),
        GastronomiaPedido.tipo_pedido.ilike(like),
        GastronomiaPedido.items.any(GastronomiaPedidoItem.nombre_producto.ilike(like)),
    ]
    digits = re.sub(r'\D+', '', text)
    if digits:
        conditions.append(GastronomiaPedido.id_pedido == int(digits))
    return query.filter(db.or_(*conditions))


def _resumen(query) -> dict:
    rows = query.with_entities(
        GastronomiaPedido.id_pedido,
        GastronomiaPedido.estado,
        GastronomiaPedido.total,
        GastronomiaPedidoPago.id_pago,
        GastronomiaPedidoPago.total_cobrado,
    ).all()
    pedidos = {}
    for pedido_id, estado, total, id_pago, total_cobrado in rows:
        data = pedidos.setdefault(int(pedido_id), {
            'estado': estado,
            'total': float(total or 0),
            'pagado': False,
            'total_pagado': 0,
        })
        if id_pago:
            data['pagado'] = True
            data['total_pagado'] += float(total_cobrado or 0)
    total_vendido = sum(data['total'] for data in pedidos.values())
    pagados = [data for data in pedidos.values() if data['pagado']]
    pendiente_pago = len(pedidos) - len(pagados)
    total_pagado = sum(data['total_pagado'] for data in pagados)
    return {
        'cantidad_historial': len(pedidos),
        'cantidad_entregada': sum(1 for data in pedidos.values() if data['estado'] == 'entregado'),
        'total_vendido': total_vendido,
        'cantidad_pagada': len(pagados),
        'cantidad_pendiente_pago': pendiente_pago,
        'total_pagado': total_pagado,
    }


def _serializar_pedidos_entregas(pedidos: list[GastronomiaPedido]) -> list[dict]:
    pedidos_data = serializar_pedidos(pedidos)
    for pedido, data in zip(pedidos, pedidos_data):
        data['fecha_entrega'] = _local_iso(pedido.fecha_entrega)
        if data.get('pago') and pedido.pago:
            data['pago']['fecha_pago'] = _local_iso(pedido.pago.fecha_pago)
    return pedidos_data


def _local_iso(value) -> str | None:
    local = utc_naive_to_local(value)
    if not local:
        return None
    return local.replace(tzinfo=None).isoformat(timespec='seconds')
