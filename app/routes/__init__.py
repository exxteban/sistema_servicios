"""
Exportación de blueprints
"""
from app.routes.main import main_bp
from app.routes.auth import auth_bp
from app.routes.productos import productos_bp
from app.routes.ventas import ventas_bp
from app.routes.caja import caja_bp
from app.routes.compras import compras_bp
from app.routes.clientes import clientes_bp
from app.routes.reportes import reportes_bp
from app.routes.reportes_tecnicos import reportes_tecnicos_bp
from app.routes.autorizaciones import bp as autorizaciones_bp
from app.routes.usuarios import usuarios_bp
from app.routes import usuarios_config_ia
from app.routes import usuarios_config_ia_backoffice
from app.routes import usuarios_config_modulos
from app.routes.tienda_api import tienda_api_bp
from app.routes.tienda_promociones_api import tienda_promociones_api_bp
from app.routes.tienda_admin import tienda_admin_bp
from app.routes.tienda_public import tienda_public_bp
from app.routes.presupuestos_empresariales import presupuestos_empresariales_bp
