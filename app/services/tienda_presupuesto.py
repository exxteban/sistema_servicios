"""Helpers publicos para adaptar consultas de tienda segun el rubro."""

from app.models.tienda import TiendaConfig
from app.models.producto import Producto
from gastronomia.services.modo_operacion import gastronomia_activa_para_cliente


DEFAULT_PRODUCT_CTA = 'Comprar por WhatsApp'
DEFAULT_CATALOG_CTA = 'Consultar'
DEFAULT_PRODUCT_MESSAGE = 'Hola, vengo de la tienda web y me interesa el producto: {producto}'
GASTRONOMIA_PRODUCT_CTA = 'Solicitar presupuesto'
GASTRONOMIA_CATALOG_CTA = 'Pedir presupuesto'


def tienda_es_gastronomia(config: TiendaConfig | None) -> bool:
    if not config:
        return False
    if gastronomia_activa_para_cliente(getattr(config, 'id_cliente', None)):
        return True
    try:
        from app.services.tienda_context import resolver_cliente_gastronomia_tienda
        cliente_gastronomia = resolver_cliente_gastronomia_tienda(config)
    except Exception:
        return False
    return bool(cliente_gastronomia and gastronomia_activa_para_cliente(cliente_gastronomia))


def config_publica_tienda(config: TiendaConfig) -> dict:
    data = config.to_public_dict()
    es_gastronomia = tienda_es_gastronomia(config)
    data['es_gastronomia'] = es_gastronomia

    if es_gastronomia:
        if not data.get('texto_cta_catalogo') or data.get('texto_cta_catalogo') == DEFAULT_CATALOG_CTA:
            data['texto_cta_catalogo'] = GASTRONOMIA_CATALOG_CTA
        if not data.get('texto_cta_producto') or data.get('texto_cta_producto') == DEFAULT_PRODUCT_CTA:
            data['texto_cta_producto'] = GASTRONOMIA_PRODUCT_CTA

    return data


def mensaje_whatsapp_producto(template: str | None, producto: Producto, config: TiendaConfig) -> str:
    plantilla = (template or '').strip()
    if tienda_es_gastronomia(config):
        if not plantilla or plantilla == DEFAULT_PRODUCT_MESSAGE:
            return _mensaje_presupuesto_gastronomia(producto)
    if plantilla:
        return _render_template_producto(plantilla, producto)
    if tienda_es_gastronomia(config):
        return _mensaje_presupuesto_gastronomia(producto)

    tipo = 'servicio' if getattr(producto, 'es_servicio', False) else 'producto'
    return f'Hola, vengo de la tienda web y me interesa el {tipo}: {producto.nombre}'


def _mensaje_presupuesto_gastronomia(producto: Producto) -> str:
    item_tipo = 'servicio' if getattr(producto, 'es_servicio', False) else 'producto'
    return (
        'Hola, vengo de la tienda web y quiero solicitar un presupuesto para gastronomia.\n'
        f'- {item_tipo.capitalize()}: {producto.nombre}\n'
        '- Cantidad requerida:\n'
        '- Fecha y hora estimada:\n'
        '- Bebidas, adicionales o servicio de atencion:\n'
        '- Comentarios:'
    )


def _render_template_producto(template: str, producto: Producto) -> str:
    precio = getattr(producto, 'precio_venta', None)
    if precio is None:
        precio = getattr(producto, 'precio', 0)
    reemplazos = {
        '{producto}': producto.nombre or '',
        '{nombre_producto}': producto.nombre or '',
        '{precio}': f"Gs. {float(precio or 0):,.0f}".replace(',', '.'),
        '{marca}': getattr(producto, 'marca', None) or '',
        '{modelo}': getattr(producto, 'modelo', None) or '',
        '{cantidad}': '',
        '{detalle_presupuesto}': '',
    }
    mensaje = template
    for token, valor in reemplazos.items():
        mensaje = mensaje.replace(token, valor)
    return mensaje
