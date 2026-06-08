"""Pantalla de pedidos recibidos desde tienda online."""
from flask import render_template
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.permisos import PERMISO_POS, requiere_permiso_gastronomia


@gastronomia_bp.route('/pedidos-tienda')
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def pedidos_tienda():
    return render_template('gastronomia/pedidos_tienda.html')
