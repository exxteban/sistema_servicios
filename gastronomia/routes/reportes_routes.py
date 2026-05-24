"""Pantalla de reportes gastronomicos."""
from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.permisos import PERMISO_REPORTES, requiere_permiso_gastronomia


@gastronomia_bp.route('/reportes')
@login_required
@requiere_permiso_gastronomia(PERMISO_REPORTES)
def reportes():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    return render_template('gastronomia/reportes.html')
