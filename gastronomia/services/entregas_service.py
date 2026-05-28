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

    tipo_pedido = (filtros.get('tipo_pedido') or '').strip().lower()
    if tipo_pedido in TIPOS_PEDIDO:
        query = query.filter(GastronomiaPedido.tipo_pedido == tipo_pedido)

    pagado = _parse_paid_filter(filtros.get('pagado'))
    if pagado is True:
        query = query.filter(GastronomiaPedidoPago.id_pago.isnot(None))
    elif pagado is False:
        query = query.filter(GastronomiaPedidoPago.id_pago.is_(None))

    query = _apply_search(query, filtros.get('q'))
    total = query.count()
    por_pagina = min(_parse_positive_int(filtros.get('per_page'), PEDIDOS_POR_PAGINA), 50)
    paginas = max(1, ceil(total / por_pagina)) if total else 1
    pagina = min(_parse_positive_int(filtros.get('page'), 1), paginas)
    fecha_operativa = db.func.coalesce(GastronomiaPedido.fecha_entrega, GastronomiaPedidoPago.fecha_pago)
    pedidos = (
        query
        .order_by(fecha_operativa.desc(), GastronomiaPedido.id_pedido.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )
    pedidos_data = serializar_pedidos(pedidos)
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
        GastronomiaPedido.total,
        GastronomiaPedidoPago.id_pago,
        GastronomiaPedidoPago.total_cobrado,
    ).all()
    total_vendido = sum(float(total or 0) for total, _id_pago, _total_cobrado in rows)
    pagados = [(id_pago, total_cobrado) for _total, id_pago, total_cobrado in rows if id_pago]
    pendiente_pago = len(rows) - len(pagados)
    total_pagado = sum(float(total_cobrado or 0) for _id_pago, total_cobrado in pagados)
    return {
        'cantidad_entregada': len(rows),
        'total_vendido': total_vendido,
        'cantidad_pagada': len(pagados),
        'cantidad_pendiente_pago': pendiente_pago,
        'total_pagado': total_pagado,
    }
