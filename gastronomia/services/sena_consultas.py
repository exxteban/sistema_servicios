"""Consultas de senas de encargos sin dependencias de servicios.

Modulo hoja: lo usan el serializador de pedidos y el cierre de caja sin
importar `adelanto_service` (que depende de `pedido_service`).
"""
from __future__ import annotations

from decimal import Decimal

from app import db
from gastronomia.encargo_models import ADELANTO_VIGENTE, GastronomiaPedidoAdelanto


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


def datos_sena_encargo(pedido, sena=None) -> dict:
    """Sena y saldo de un encargo para el operador (cocina los oculta)."""
    if sena is None:
        sena = senas_vigentes_por_pedido([pedido.id_pedido]).get(int(pedido.id_pedido), Decimal('0.00'))
    return {'sena_vigente': float(sena), 'saldo': float(saldo_encargo(pedido.total, sena))}


def saldo_encargo(total, sena) -> Decimal:
    saldo = Decimal(str(total or 0)) - Decimal(str(sena or 0))
    return max(saldo, Decimal('0.00')).quantize(Decimal('0.01'))
