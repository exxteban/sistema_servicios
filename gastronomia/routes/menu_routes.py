"""Vistas HTML para configurar el menu gastronomico."""
from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.menu_service import listar_categorias, listar_productos
from gastronomia.services.menu_tv_service import obtener_o_preparar_config_tv, serializar_config_tv
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia


@gastronomia_bp.route('/menu')
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def menu_config():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    categorias = listar_categorias(cliente_id)
    productos = listar_productos(cliente_id)
    menu_tv_config = obtener_o_preparar_config_tv(cliente_id)
    menu_tv_data = serializar_config_tv(menu_tv_config) if menu_tv_config else None
    return render_template(
        'gastronomia/menu_config.html',
        categorias=categorias,
        productos=productos,
        menu_tv_config=menu_tv_data,
        menu_tv_public_url=(
            url_for('gastronomia.menu_tv_publico', slug=menu_tv_data['slug'])
            if menu_tv_data else ''
        ),
    )
