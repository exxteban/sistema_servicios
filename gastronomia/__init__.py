"""Modulo aislado para el modo Gastronomia."""
from gastronomia import bi_models as _bi_models  # noqa: F401
from gastronomia import sugerencias_models as _sugerencias_models  # noqa: F401
from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.routes.api_routes import gastronomia_api_bp
from gastronomia.routes.channel_price_api_routes import gastronomia_channel_price_api_bp
from gastronomia.routes.caja_api_routes import gastronomia_caja_api_bp
from gastronomia.routes.cocina_api_routes import gastronomia_cocina_api_bp
from gastronomia.routes.delivery_api_routes import gastronomia_delivery_api_bp
from gastronomia.routes.encargos_api_routes import gastronomia_encargos_api_bp
from gastronomia.routes.entregas_api_routes import gastronomia_entregas_api_bp
from gastronomia.routes.menu_tv_api_routes import gastronomia_menu_tv_api_bp
from gastronomia.routes.menu_plantillas_api_routes import gastronomia_menu_plantillas_api_bp
from gastronomia.routes.menu_combo_api_routes import gastronomia_menu_combo_api_bp
from gastronomia.routes.pedido_api_routes import gastronomia_pedidos_api_bp
from gastronomia.routes.produccion_api_routes import gastronomia_produccion_api_bp
from gastronomia.routes.reportes_api_routes import gastronomia_reportes_api_bp
from gastronomia.routes.salon_api_routes import gastronomia_salon_api_bp
from gastronomia.routes.stock_api_routes import gastronomia_stock_api_bp
from gastronomia.routes import bi_routes as _bi_routes  # noqa: F401
from gastronomia.routes import bi_cola_routes as _bi_cola_routes  # noqa: F401
from gastronomia.routes import caja_routes as _caja_routes  # noqa: F401
from gastronomia.routes import cocina_routes as _cocina_routes  # noqa: F401
from gastronomia.routes import delivery_routes as _delivery_routes  # noqa: F401
from gastronomia.routes import encargos_routes as _encargos_routes  # noqa: F401
from gastronomia.routes import importacion_api_routes as _importacion_api_routes  # noqa: F401
from gastronomia.routes import importacion_routes as _importacion_routes  # noqa: F401
from gastronomia.routes import entregas_routes as _entregas_routes  # noqa: F401
from gastronomia.routes import menu_routes as _menu_routes  # noqa: F401
from gastronomia.routes import sugerencias_routes as _sugerencias_routes  # noqa: F401
from gastronomia.routes import sugerencias_api_routes as _sugerencias_api_routes  # noqa: F401
from gastronomia.routes import menu_tv_routes as _menu_tv_routes  # noqa: F401
from gastronomia.routes import pos_routes as _pos_routes  # noqa: F401
from gastronomia.routes import produccion_routes as _produccion_routes  # noqa: F401
from gastronomia.routes import public_routes as _public_routes  # noqa: F401
from gastronomia.routes import reportes_routes as _reportes_routes  # noqa: F401
from gastronomia.routes import salon_routes as _salon_routes  # noqa: F401
from gastronomia.routes import tienda_pedidos_routes as _tienda_pedidos_routes  # noqa: F401


__all__ = [
    'gastronomia_bp',
    'gastronomia_api_bp',
    'gastronomia_channel_price_api_bp',
    'gastronomia_caja_api_bp',
    'gastronomia_cocina_api_bp',
    'gastronomia_delivery_api_bp',
    'gastronomia_encargos_api_bp',
    'gastronomia_entregas_api_bp',
    'gastronomia_menu_tv_api_bp',
    'gastronomia_menu_plantillas_api_bp',
    'gastronomia_menu_combo_api_bp',
    'gastronomia_pedidos_api_bp',
    'gastronomia_produccion_api_bp',
    'gastronomia_reportes_api_bp',
    'gastronomia_salon_api_bp',
    'gastronomia_stock_api_bp',
]
