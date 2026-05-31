"""Calculos monetarios para devoluciones parciales."""
from decimal import Decimal

from app.services.promociones_calculo import money


def calculate_refund_subtotal(
    *,
    line_subtotal,
    original_quantity,
    returned_quantity,
    returned_subtotal,
    quantity,
) -> Decimal:
    """Distribuye el saldo historico y reconcilia el ultimo reintegro."""
    available_quantity = int(original_quantity or 0) - int(returned_quantity or 0)
    refund_quantity = int(quantity or 0)
    if available_quantity <= 0 or refund_quantity <= 0 or refund_quantity > available_quantity:
        raise ValueError('Cantidad invalida para devolucion')

    remaining_subtotal = money(Decimal(str(line_subtotal or 0)) - Decimal(str(returned_subtotal or 0)))
    if refund_quantity == available_quantity:
        return remaining_subtotal
    return money((remaining_subtotal * refund_quantity) / available_quantity)
