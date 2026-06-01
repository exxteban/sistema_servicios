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


def normalize_store_media_url(url: str | None) -> str:
    value = (url or '').strip()
    if not value:
        return ''
    value = value.replace('\\', '/')
    if value.startswith(('data:', 'blob:')):
        return value

    lower_value = value.lower()
    media_marker = '/api/tienda/media/'
    if media_marker in lower_value:
        idx = lower_value.index(media_marker) + len(media_marker)
        return f"/api/tienda/media/{value[idx:].lstrip('/')}"

    static_upload_marker = 'static/tienda_uploads/'
    if static_upload_marker in lower_value:
        idx = lower_value.index(static_upload_marker) + len(static_upload_marker)
        return f"/api/tienda/media/{value[idx:].lstrip('/')}"

    upload_marker = 'tienda_uploads/'
    if upload_marker in lower_value:
        idx = lower_value.index(upload_marker) + len(upload_marker)
        return f"/api/tienda/media/{value[idx:].lstrip('/')}"

    if re.match(r'^(?:[a-z]+:)?//', value, flags=re.IGNORECASE):
        return value

    match_static = re.search(r'(?:^|/)(static/.*)$', value, flags=re.IGNORECASE)
    if match_static:
        static_rel_path = match_static.group(1).lstrip('/')
        return f'/{static_rel_path}'

    return value if value.startswith('/') else f'/{value}'
