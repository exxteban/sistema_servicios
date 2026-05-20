import re
import unicodedata


def slugify_tienda_text(value: str | None, fallback: str = 'producto') -> str:
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    without_marks = ''.join(char for char in normalized if not unicodedata.combining(char))
    lowered = without_marks.lower()
    collapsed = re.sub(r'[^a-z0-9]+', '-', lowered).strip('-')
    return collapsed[:80] or fallback


def build_product_public_path(store_slug: str, product_id: int, product_name: str | None) -> str:
    product_slug = slugify_tienda_text(product_name, fallback=str(product_id))
    return f'/tienda/{store_slug}/producto/{product_id}-{product_slug}'


def build_category_public_path(store_slug: str, category_name: str | None) -> str:
    category_slug = slugify_tienda_text(category_name, fallback='catalogo')
    return f'/tienda/{store_slug}/categoria/{category_slug}'
