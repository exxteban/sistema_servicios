"""Dashboard inicial del modo Gastronomia."""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.modo_operacion import gastronomia_activa
from gastronomia.services.permisos import (
    PERMISO_CAJA,
    PERMISO_COCINA,
    PERMISO_MENU,
    PERMISO_POS,
    PERMISO_REPORTES,
    PERMISO_SALON,
    tiene_permiso_gastronomia,
)


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
    permisos = {
        'menu': tiene_permiso_gastronomia(PERMISO_MENU),
        'pos': tiene_permiso_gastronomia(PERMISO_POS),
        'salon': tiene_permiso_gastronomia(PERMISO_SALON),
        'cocina': tiene_permiso_gastronomia(PERMISO_COCINA),
        'caja': tiene_permiso_gastronomia(PERMISO_CAJA),
        'reportes': tiene_permiso_gastronomia(PERMISO_REPORTES),
    }

    return render_template(
        'gastronomia/dashboard.html',
        modo_disponible=True,
        contexto_operativo=bool(cliente_id),
        cliente=getattr(current_user, 'cliente', None),
        permisos=permisos,
    )
