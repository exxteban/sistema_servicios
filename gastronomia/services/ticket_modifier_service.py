"""Formato compartido de modificadores para tickets gastronómicos."""
from decimal import Decimal, InvalidOperation

from gastronomia.models import GastronomiaPedidoItemModificador


def modifier_ticket_lines(item) -> list[str]:
    modifiers = item.modificadores.order_by(
        GastronomiaPedidoItemModificador.id_modificador.asc(),
    ).all()
    return [format_ticket_modifier(modifier) for modifier in modifiers]


def format_ticket_modifier(modifier) -> str:
    name = str(getattr(modifier, 'nombre_opcion', '') or '').strip()
    group_type = str(getattr(modifier, 'tipo_grupo', '') or '').strip()
    if group_type == 'ingrediente_removible' and not name.lower().startswith('sin '):
        name = f'Sin {name}'

    delta = _decimal_value(getattr(modifier, 'precio_delta', 0))
    if not delta:
        return name

    sign = '+' if delta > 0 else '-'
    amount = f'{abs(delta):,.0f}'.replace(',', '.')
    return f'{name} {sign}Gs. {amount}'


def _decimal_value(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')
