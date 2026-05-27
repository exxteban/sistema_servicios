"""Modulo aislado para el modo Gastronomia."""
from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.routes.api_routes import gastronomia_api_bp
from gastronomia.routes.caja_api_routes import gastronomia_caja_api_bp
from gastronomia.routes.cocina_api_routes import gastronomia_cocina_api_bp
from gastronomia.routes.entregas_api_routes import gastronomia_entregas_api_bp
from gastronomia.routes.menu_tv_api_routes import gastronomia_menu_tv_api_bp
from gastronomia.routes.pedido_api_routes import gastronomia_pedidos_api_bp
from gastronomia.routes.reportes_api_routes import gastronomia_reportes_api_bp
from gastronomia.routes.salon_api_routes import gastronomia_salon_api_bp
from gastronomia.routes import caja_routes as _caja_routes  # noqa: F401
from gastronomia.routes import cocina_routes as _cocina_routes  # noqa: F401
from gastronomia.routes import entregas_routes as _entregas_routes  # noqa: F401
from gastronomia.routes import menu_routes as _menu_routes  # noqa: F401
from gastronomia.routes import menu_tv_routes as _menu_tv_routes  # noqa: F401
from gastronomia.routes import pos_routes as _pos_routes  # noqa: F401
from gastronomia.routes import reportes_routes as _reportes_routes  # noqa: F401
from gastronomia.routes import salon_routes as _salon_routes  # noqa: F401


__all__ = [
    'gastronomia_bp',
    'gastronomia_api_bp',
    'gastronomia_caja_api_bp',
    'gastronomia_cocina_api_bp',
    'gastronomia_entregas_api_bp',
    'gastronomia_menu_tv_api_bp',
    'gastronomia_pedidos_api_bp',
    'gastronomia_reportes_api_bp',
    'gastronomia_salon_api_bp',
]
