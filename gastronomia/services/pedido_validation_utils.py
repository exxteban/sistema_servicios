"""Parseos auxiliares para pedidos gastronomicos."""
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import parse_qs, unquote, urlparse


def parse_estimated_minutes(value) -> int | None:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return None
    if minutes <= 0:
        return None
    return min(minutes, 1440)


def parse_nonnegative_money(value) -> Decimal:
    if value in (None, ''):
        return Decimal('0.00')
    try:
        amount = Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Monto invalido.') from exc
    if amount < 0:
        raise ValueError('El costo de envio no puede ser negativo.')
    return amount


def parse_optional_positive_int(value) -> int | None:
    if value in (None, ''):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def parse_optional_coordinate(value, minimum: float, maximum: float) -> float | None:
    if value in (None, ''):
        return None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if minimum <= parsed <= maximum else None


def coords_from_location_text(value: str) -> tuple[float | None, float | None]:
    text_value = unquote(str(value or '').strip())
    match = re.search(r'!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)', text_value)
    if match:
        return _validated_coords(match.group(1), match.group(2))
    parsed = urlparse(text_value)
    params = parse_qs(parsed.query)
    for key in ('q', 'query', 'll', 'destination'):
        if params.get(key):
            coords = _coords_from_plain_text(params[key][0])
            if coords != (None, None):
                return coords
    match = re.search(r'@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)', text_value)
    if match:
        return _validated_coords(match.group(1), match.group(2))
    return _coords_from_plain_text(text_value)


def _coords_from_plain_text(value: str) -> tuple[float | None, float | None]:
    match = re.search(r'(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)', str(value or ''))
    if not match:
        return None, None
    return _validated_coords(match.group(1), match.group(2))


def _validated_coords(lat_value, lng_value) -> tuple[float | None, float | None]:
    lat = parse_optional_coordinate(lat_value, -90, 90)
    lng = parse_optional_coordinate(lng_value, -180, 180)
    if lat is None or lng is None:
        return None, None
    return lat, lng
