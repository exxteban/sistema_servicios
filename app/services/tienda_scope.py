from app import db
from app.models.producto import Categoria, Producto
from app.models.tienda import TiendaConfig
from app.utils.tienda_urls import slugify_tienda_text


def _single_active_store() -> bool:
    return TiendaConfig.query.filter_by(activa=True).count() <= 1


def store_product_scope_filter(config: TiendaConfig):
    """Scope público por tienda con fallback legacy para instalaciones mono-tienda."""
    if _single_active_store():
        return db.or_(
            Producto.id_cliente == config.id_cliente,
            Producto.id_cliente.is_(None),
        )
    return Producto.id_cliente == config.id_cliente


def public_product_query(config: TiendaConfig):
    return Producto.query.filter(
        Producto.publicado_tienda.is_(True),
        Producto.activo.is_(True),
        store_product_scope_filter(config),
    )


def public_category_query(config: TiendaConfig):
    return (
        db.session.query(Categoria)
        .join(Producto, Producto.id_categoria == Categoria.id_categoria)
        .filter(
            Categoria.activo.is_(True),
            Producto.publicado_tienda.is_(True),
            Producto.activo.is_(True),
            store_product_scope_filter(config),
        )
        .distinct()
    )


def find_public_category_by_slug(config: TiendaConfig, category_slug: str | None):
    normalized_slug = slugify_tienda_text(category_slug, fallback='catalogo')
    for category in public_category_query(config).order_by(Categoria.nombre.asc()).all():
        if slugify_tienda_text(category.nombre, fallback=str(category.id_categoria)) == normalized_slug:
            return category
    return None
