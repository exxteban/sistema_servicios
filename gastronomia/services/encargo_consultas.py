"""Consultas de encargos (senas y fotos) sin dependencias de servicios.

Modulo hoja: lo usan el serializador de pedidos, el modelo y el cierre de caja
sin importar `adelanto_service` ni `encargo_foto_service` (que dependen de
`pedido_service`).
"""
from __future__ import annotations

from decimal import Decimal

from app import db
from gastronomia.encargo_models import ADELANTO_VIGENTE, GastronomiaPedidoAdelanto, GastronomiaPedidoFoto


def senas_vigentes_por_pedido(pedido_ids) -> dict[int, Decimal]:
    """Suma de adelantos vigentes por pedido, en una sola consulta."""
    ids = [int(pedido_id) for pedido_id in pedido_ids or []]
    if not ids:
        return {}
    filas = (
        db.session.query(GastronomiaPedidoAdelanto.pedido_id, db.func.sum(GastronomiaPedidoAdelanto.monto))
        .filter(
            GastronomiaPedidoAdelanto.pedido_id.in_(ids),
            GastronomiaPedidoAdelanto.estado == ADELANTO_VIGENTE,
        )
        .group_by(GastronomiaPedidoAdelanto.pedido_id)
        .all()
    )
    return {int(pedido_id): Decimal(str(total or 0)).quantize(Decimal('0.01')) for pedido_id, total in filas}


def datos_encargo(pedido, *, sena=None, fotos=None) -> dict:
    """Sena, saldo y fotos de un encargo. Cocina ve las fotos pero oculta sena y saldo."""
    if sena is None:
        sena = senas_vigentes_por_pedido([pedido.id_pedido]).get(int(pedido.id_pedido), Decimal('0.00'))
    if fotos is None:
        fotos = fotos_por_pedido([pedido.id_pedido]).get(int(pedido.id_pedido), [])
    return {'sena_vigente': float(sena), 'saldo': float(saldo_encargo(pedido.total, sena)), 'fotos': fotos}


def saldo_encargo(total, sena) -> Decimal:
    saldo = Decimal(str(total or 0)) - Decimal(str(sena or 0))
    return max(saldo, Decimal('0.00')).quantize(Decimal('0.01'))


def fotos_por_pedido(pedido_ids) -> dict[int, list[dict]]:
    """Fotos de referencia de varios pedidos en una consulta."""
    ids = [int(pedido_id) for pedido_id in pedido_ids or []]
    if not ids:
        return {}
    resultado: dict[int, list[dict]] = {}
    fotos = (
        GastronomiaPedidoFoto.query
        .filter(GastronomiaPedidoFoto.pedido_id.in_(ids))
        .order_by(GastronomiaPedidoFoto.orden.asc(), GastronomiaPedidoFoto.id_foto.asc())
        .all()
    )
    for foto in fotos:
        resultado.setdefault(int(foto.pedido_id), []).append(foto.to_dict())
    return resultado
