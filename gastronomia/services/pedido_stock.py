"""Politica de stock por pedido: cuando se consume y cuando se restaura.

Un pedido comun consume stock al crear cada item (comportamiento de siempre).
Un encargo lo difiere: consume recien al entrar en produccion (`preparando`),
no al tomarlo ni al editarlo. Ver docs/pasteleria_fase1_diseno.md, punto A.
"""
from __future__ import annotations

from gastronomia.models import GastronomiaPedido
from gastronomia.services.stock_service import consumir_stock_item, restaurar_stock_items
from gastronomia.stock_models import GastronomiaPedidoItemConsumo


# Estados desde los cuales un encargo ya tiene que haber consumido su stock.
ESTADOS_CON_STOCK_CONSUMIDO = {'preparando', 'listo', 'en_camino', 'entregado', 'cobrado'}


def pedido_difiere_stock(pedido: GastronomiaPedido) -> bool:
    return bool(getattr(pedido, 'es_encargo', False))


def consumir_stock_pedido(pedido: GastronomiaPedido) -> list[dict]:
    """Consume los items que todavia no tienen consumo activo (idempotente)."""
    items = pedido.items.all()
    ya_consumidos = _item_ids_con_consumo_activo(items)
    alertas: list[dict] = []
    for item in items:
        if int(item.id_item) in ya_consumidos:
            continue
        alertas.extend(consumir_stock_item(item))
    return alertas


def restaurar_stock_pedido(pedido: GastronomiaPedido) -> None:
    """Restaura solo lo realmente consumido; sin consumos activos no hace nada."""
    restaurar_stock_items(pedido.items.all())


def aplicar_stock_por_transicion(pedido: GastronomiaPedido, estado_anterior: str, estado_nuevo: str) -> None:
    """Unico lugar que decide el stock al cambiar el estado de un pedido."""
    if pedido_difiere_stock(pedido):
        _transicion_encargo(pedido, estado_anterior, estado_nuevo)
    else:
        _transicion_pedido_comun(pedido, estado_anterior, estado_nuevo)


def _transicion_pedido_comun(pedido, estado_anterior: str, estado_nuevo: str) -> None:
    if estado_nuevo == 'cancelado' and estado_anterior != 'cancelado':
        restaurar_stock_pedido(pedido)
    elif estado_nuevo != 'cancelado' and estado_anterior == 'cancelado':
        for item in pedido.items.all():
            consumir_stock_item(item)


def _transicion_encargo(pedido, estado_anterior: str, estado_nuevo: str) -> None:
    if estado_nuevo == 'cancelado':
        if estado_anterior != 'cancelado':
            restaurar_stock_pedido(pedido)
        return
    if estado_nuevo in ESTADOS_CON_STOCK_CONSUMIDO:
        consumir_stock_pedido(pedido)


def _item_ids_con_consumo_activo(items) -> set[int]:
    item_ids = [int(item.id_item) for item in items if item.id_item]
    if not item_ids:
        return set()
    filas = (
        GastronomiaPedidoItemConsumo.query
        .with_entities(GastronomiaPedidoItemConsumo.item_id)
        .filter(
            GastronomiaPedidoItemConsumo.item_id.in_(item_ids),
            GastronomiaPedidoItemConsumo.restaurado.is_(False),
        )
        .distinct()
        .all()
    )
    return {int(fila[0]) for fila in filas}
