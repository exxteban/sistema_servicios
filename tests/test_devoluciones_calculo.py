from decimal import Decimal

from app.services.devoluciones_calculo import calculate_refund_subtotal


def test_reconcilia_el_ultimo_reintegro_de_una_linea_promocionada():
    first = calculate_refund_subtotal(
        line_subtotal=50000,
        original_quantity=3,
        returned_quantity=0,
        returned_subtotal=0,
        quantity=1,
    )
    second = calculate_refund_subtotal(
        line_subtotal=50000,
        original_quantity=3,
        returned_quantity=1,
        returned_subtotal=first,
        quantity=1,
    )
    last = calculate_refund_subtotal(
        line_subtotal=50000,
        original_quantity=3,
        returned_quantity=2,
        returned_subtotal=first + second,
        quantity=1,
    )

    assert first == Decimal('16666.67')
    assert second == Decimal('16666.67')
    assert last == Decimal('16666.66')
    assert first + second + last == Decimal('50000')
