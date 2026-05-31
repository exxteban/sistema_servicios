"""Adaptadores de promociones para flujos de venta y cola de cobro."""
from decimal import Decimal

from app.services.promociones_calculo import calculate_promotion_totals
from app.services.tienda_promociones import (
    get_active_product_promotion_map_any_client,
    serialize_public_promotion,
)


def get_queue_product_promotions(items) -> dict:
    product_ids = []
    for item in items or []:
        if (item.get('tipo') or 'producto').strip().lower() == 'servicio':
            continue
        if item.get('id_servicio') not in (None, ''):
            continue
        try:
            product_ids.append(int(item.get('id_producto')))
        except Exception:
            continue
    return get_active_product_promotion_map_any_client(product_ids)


def calculate_queue_product_subtotal(
    *,
    producto,
    precio,
    cantidad,
    precio_opcion_id,
    precio_manual,
    usar_precio_mayorista,
    promotions,
) -> tuple[Decimal, dict | None]:
    subtotal = Decimal(str(precio)) * int(cantidad)
    if precio_opcion_id not in (None, '') or precio_manual or usar_precio_mayorista:
        return subtotal, None

    promotion = promotions.get(int(producto.id_producto))
    if not promotion:
        return subtotal, None

    metrics = calculate_promotion_totals(precio, cantidad, promotion)
    return metrics['subtotal_base'], serialize_public_promotion(promotion, include_products=False)


def get_serialized_active_product_promotions(product_ids) -> dict[int, dict]:
    promotions = get_active_product_promotion_map_any_client(product_ids)
    return {
        int(product_id): serialize_public_promotion(promotion, include_products=False)
        for product_id, promotion in promotions.items()
    }
