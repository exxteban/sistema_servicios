"""Dashboard inicial del modo Gastronomia."""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.dashboard_permisos import permisos_dashboard
from gastronomia.services.dashboard_preferences import build_dashboard_cards, build_dashboard_groups
from gastronomia.services.dashboard_resumen_service import badges_dashboard, resumen_dashboard
from gastronomia.services.modo_operacion import gastronomia_activa


gastronomia_bp = Blueprint(
    'gastronomia',
    __name__,
    template_folder='../templates',
    static_folder='../static',
)


@gastronomia_bp.route('/')
@login_required
def dashboard():
    if not gastronomia_activa():
        flash('Gastronomia no esta activa en esta instalacion.', 'warning')
        return redirect(url_for('main.dashboard'))

    cliente_id = cliente_id_actual_gastronomia()
    permisos = permisos_dashboard(cliente_id)
    resumen = resumen_dashboard(cliente_id, current_user, permisos)
    dashboard_cards = build_dashboard_cards(
        current_user,
        permisos,
        contexto_operativo=bool(cliente_id),
        pedidos_pendientes_caja=resumen['caja_pendientes'],
        pedidos_pendientes_tienda=resumen['tienda_pendientes'],
    )

    return render_template(
        'gastronomia/dashboard.html',
        modo_disponible=True,
        contexto_operativo=bool(cliente_id),
        cliente=getattr(current_user, 'cliente', None),
        permisos=permisos,
        resumen=resumen,
        dashboard_groups=build_dashboard_groups(dashboard_cards, badges_dashboard(resumen)),
    )
