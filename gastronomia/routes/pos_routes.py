"""Pantalla POS touch para toma de pedidos."""
from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.menu_service import listar_categorias
from gastronomia.services.permisos import PERMISO_POS, requiere_permiso_gastronomia


@gastronomia_bp.route('/pos')
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def pos():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    return render_template(
        'gastronomia/pos.html',
        categorias=listar_categorias(cliente_id, incluir_ocultas=False),
        mesa_inicial=(request.args.get('mesa') or '').strip()[:40],
    )
