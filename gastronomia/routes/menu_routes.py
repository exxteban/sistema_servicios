"""Vistas HTML para configurar el menu gastronomico."""
from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.menu_service import listar_categorias, listar_productos
from gastronomia.services.menu_tv_service import obtener_o_preparar_config_tv, serializar_config_tv
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia


@gastronomia_bp.route('/menu')
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def menu_config():
    from app.models.tienda import TiendaConfig
    from app.services.tienda_promociones import list_admin_promotions, serialize_admin_promotion

    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    categorias = listar_categorias(cliente_id)
    productos = listar_productos(cliente_id)
    menu_tv_config = obtener_o_preparar_config_tv(cliente_id)
    menu_tv_data = serializar_config_tv(menu_tv_config) if menu_tv_config else None
    puede_gestionar_promociones = current_user.es_admin() or current_user.tiene_permiso('editar_configuracion')
    tienda_config = TiendaConfig.query.filter_by(id_cliente=int(cliente_id)).first()
    promociones = []
    if puede_gestionar_promociones:
        promociones = [
            serialize_admin_promotion(item)
            for item in list_admin_promotions(int(cliente_id))
            if item.gastronomia_productos_rel
        ]
    return render_template(
        'gastronomia/menu_config.html',
        categorias=categorias,
        productos=productos,
        menu_tv_config=menu_tv_data,
        puede_gestionar_promociones=puede_gestionar_promociones,
        promociones=promociones,
        promociones_catalogo='gastronomia',
        promociones_cliente_gastronomia_id=int(cliente_id),
        promociones_return_url=url_for(
            'gastronomia.menu_config',
            gastro_main_tab='menu-cargado',
            gastro_menu_tab='promociones',
        ),
        tienda_config=tienda_config,
        menu_tv_public_url=(
            url_for('gastronomia.menu_tv_publico', slug=menu_tv_data['slug'])
            if menu_tv_data else ''
        ),
    )
