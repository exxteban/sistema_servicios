import re
import unicodedata
from functools import lru_cache


ELECTRONICS_BRANDS = (
    {'brand': 'Samsung', 'slug': 'samsung', 'aliases': ('samsung',)},
    {'brand': 'Apple', 'slug': 'apple', 'aliases': ('apple', 'iphone', 'ipad', 'macbook', 'imac', 'mac')},
    {'brand': 'Xiaomi', 'slug': 'xiaomi', 'aliases': ('xiaomi', 'redmi', 'poco', 'mi ')},
    {'brand': 'Motorola', 'slug': 'motorola', 'aliases': ('motorola', 'moto g', 'moto e', 'moto edge', 'moto')},
    {'brand': 'Huawei', 'slug': 'huawei', 'aliases': ('huawei', 'honor')},
    {'brand': 'Sony', 'slug': 'sony', 'aliases': ('sony', 'xperia', 'playstation', 'ps4', 'ps5')},
    {'brand': 'LG', 'slug': 'lg', 'aliases': ('lg',)},
    {'brand': 'Lenovo', 'slug': 'lenovo', 'aliases': ('lenovo',)},
    {'brand': 'Dell', 'slug': 'dell', 'aliases': ('dell',)},
    {'brand': 'HP', 'slug': 'hp', 'aliases': ('hp', 'hewlett packard', 'hewlett-packard')},
    {'brand': 'Asus', 'slug': 'asus', 'aliases': ('asus', 'rog')},
    {'brand': 'Acer', 'slug': 'acer', 'aliases': ('acer',)},
    {'brand': 'Nokia', 'slug': 'nokia', 'aliases': ('nokia',)},
    {'brand': 'OnePlus', 'slug': 'oneplus', 'aliases': ('oneplus', 'one plus')},
    {'brand': 'Oppo', 'slug': 'oppo', 'aliases': ('oppo',)},
    {'brand': 'Vivo', 'slug': 'vivo', 'aliases': ('vivo',)},
    {'brand': 'Realme', 'slug': 'realme', 'aliases': ('realme',)},
    {'brand': 'TCL', 'slug': 'tcl', 'aliases': ('tcl',)},
    {'brand': 'Microsoft', 'slug': 'microsoft', 'aliases': ('microsoft', 'surface', 'xbox')},
    {'brand': 'Google', 'slug': 'google', 'aliases': ('google', 'pixel')},
)

WIDE_LOGO_SLUGS = {'samsung', 'sony', 'lenovo', 'acer', 'asus', 'oneplus', 'oppo', 'vivo', 'realme', 'tcl'}


def normalize_brand_text(value):
    text = str(value or '').strip().lower()
    if not text:
        return ''
    text = unicodedata.normalize('NFD', text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _matches_alias(normalized_text, aliases):
    padded_text = f' {normalized_text} '
    for alias in aliases:
        normalized_alias = normalize_brand_text(alias)
        if not normalized_alias:
            continue
        if normalized_text == normalized_alias:
            return True
        if normalized_text.startswith(f'{normalized_alias} '):
            return True
        if f' {normalized_alias} ' in padded_text:
            return True
    return False


def _fallback_label(brand):
    words = [word for word in normalize_brand_text(brand).split() if word]
    if len(words) > 1:
        return ''.join(word[:1] for word in words[:2]).upper()
    return (words[0][:2] if words else '').upper()


@lru_cache(maxsize=512)
def resolve_electronics_brand_logo(text):
    normalized = normalize_brand_text(text)
    if not normalized:
        return None

    for spec in ELECTRONICS_BRANDS:
        if _matches_alias(normalized, spec['aliases']):
            slug = spec['slug']
            fallback_url = f'https://www.google.com/s2/favicons?domain={slug}.com&sz=64'
            return {
                'brand': spec['brand'],
                'url': f'https://cdn.simpleicons.org/{slug}?viewbox=auto',
                'fallback_url': fallback_url,
                'fallback_urls': (fallback_url,),
                'fallback_label': _fallback_label(spec['brand']),
                'is_wide': slug in WIDE_LOGO_SLUGS,
            }
    return None
