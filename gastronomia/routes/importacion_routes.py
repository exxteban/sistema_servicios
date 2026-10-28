"""Pantalla para importar ventas historicas desde Excel."""
from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.permisos import PERMISO_CAJA, PERMISO_REPORTES, requiere_permiso_gastronomia


@gastronomia_bp.route('/importar-ventas')
@login_required
@requiere_permiso_gastronomia(PERMISO_REPORTES)
@requiere_permiso_gastronomia(PERMISO_CAJA)
def importar_ventas():
    if not cliente_id_actual_gastronomia():
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    return render_template('gastronomia/importar_ventas.html')
