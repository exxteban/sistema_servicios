"""Helpers publicos para publicar promociones segun el catalogo de tienda."""


def is_public_store_product(product, catalog_type: str, client_id: int) -> bool:
    if not product or not bool(product.activo):
        return False
    product_client_id = getattr(product, 'cliente_id' if catalog_type == 'gastronomia' else 'id_cliente', None)
    if product_client_id not in (None, int(client_id)):
        return False
    if catalog_type == 'gastronomia':
        return bool(product.visible and product.publicado_tienda and product.disponible)
    return bool(product.publicado_tienda)


def store_promotion_catalog_type(config) -> str:
    from app.services.tienda_presupuesto import tienda_es_gastronomia

    return 'gastronomia' if tienda_es_gastronomia(config) else 'producto'
