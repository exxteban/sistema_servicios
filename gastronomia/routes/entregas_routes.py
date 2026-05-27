"""Vista interna de entregas gastronomicas."""
from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.permisos import (
    PERMISO_CAJA,
    PERMISO_COCINA,
    PERMISO_SALON,
    requiere_permiso_gastronomia,
)


@gastronomia_bp.route('/entregas')
@login_required
@requiere_permiso_gastronomia(PERMISO_CAJA, PERMISO_COCINA, PERMISO_SALON)
def entregas():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    return render_template('gastronomia/entregas.html')
