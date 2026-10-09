"""Selección del motor de FE de esta instalación."""

PROVEEDOR_PROPIO = 'propio'
PROVEEDOR_API = 'api'
PROVEEDORES = (
    (PROVEEDOR_PROPIO, 'Motor propio (SIFEN directo)'),
    (PROVEEDOR_API, 'API externa'),
)


def obtener_proveedor(config=None):
    """Instancia el proveedor configurado. Import perezoso: el módulo de la API
    importa servicios que a su vez importan esta función."""
    if config is None:
        from facturacion_electronica.services.config_service import obtener_configuracion
        config = obtener_configuracion()
    nombre = getattr(config, 'proveedor', PROVEEDOR_PROPIO) or PROVEEDOR_PROPIO
    if nombre == PROVEEDOR_API:
        from facturacion_electronica.services.proveedores.api import ProveedorApi
        return ProveedorApi()
    from facturacion_electronica.services.proveedores.propio import ProveedorPropio
    return ProveedorPropio()
