"""Pantalla publica de menu para televisores."""
from flask import abort, render_template

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.menu_tv_service import obtener_payload_publico


@gastronomia_bp.route('/menu-tv/<slug>')
def menu_tv_publico(slug):
    if obtener_payload_publico(slug) is None:
        abort(404)
    return render_template('gastronomia/menu_tv.html', slug=slug)
