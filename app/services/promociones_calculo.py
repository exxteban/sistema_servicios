"""Calculo compartido de promociones para productos y gastronomia."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


TWOPLACES = Decimal('0.01')


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def promotion_description(promotion) -> str:
    tipo = str(getattr(promotion, 'tipo', '') or '').strip()
    if tipo == 'cantidad':
        return f"{int(getattr(promotion, 'cantidad_lleva', 0) or 0)}x{int(getattr(promotion, 'cantidad_paga', 0) or 0)}"
    if tipo == 'porcentaje':
        return f"{money(getattr(promotion, 'valor', 0))}% de descuento"
    if tipo == 'monto_fijo':
        return f"Descuento de {money(getattr(promotion, 'valor', 0))}"
    if tipo == 'precio_promocional':
        return f"Precio promocional {money(getattr(promotion, 'valor', 0))}"
    return str(getattr(promotion, 'nombre', '') or 'Promocion')


def calculate_promotion_totals(base_unit_price, quantity, promotion=None) -> dict:
    """Calcula solo el precio base; los modificadores se suman por separado."""
    base_price = money(base_unit_price)
    qty = max(int(quantity or 0), 0)
    gross = money(base_price * qty)
    subtotal = gross
    bonified_quantity = 0
    tipo = str(getattr(promotion, 'tipo', '') or '').strip()

    if promotion and tipo == 'porcentaje':
        percentage = money(getattr(promotion, 'valor', 0))
        subtotal = gross - ((gross * percentage) / Decimal('100'))
    elif promotion and tipo == 'monto_fijo':
        subtotal = (base_price - money(getattr(promotion, 'valor', 0))) * qty
    elif promotion and tipo == 'precio_promocional':
        subtotal = money(getattr(promotion, 'valor', 0)) * qty
    elif promotion and tipo == 'cantidad':
        takes = int(getattr(promotion, 'cantidad_lleva', 0) or 0)
        pays = int(getattr(promotion, 'cantidad_paga', 0) or 0)
        if takes > 0 and 0 <= pays < takes:
            bonified_quantity = (qty // takes) * (takes - pays)
            subtotal = base_price * (qty - bonified_quantity)

    subtotal = money(max(subtotal, Decimal('0')))
    discount = money(max(gross - subtotal, Decimal('0')))
    effective_unit_price = money(subtotal / qty) if qty else base_price
    return {
        'precio_base': base_price,
        'precio_unitario_efectivo': effective_unit_price,
        'subtotal_base': subtotal,
        'subtotal_base_original': gross,
        'descuento_linea': discount,
        'cantidad_bonificada': bonified_quantity,
        'descripcion': promotion_description(promotion) if promotion else None,
    }
