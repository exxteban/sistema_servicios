"""Version imprimible del reporte de valor del mes (BI-03)."""
from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.bi.reporte_valor import resumen_reporte_valor_seguro
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia


@gastronomia_bp.route('/bi/reporte')
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def bi_reporte_imprimible():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    return render_template('gastronomia/bi_reporte_imprimible.html', reporte=resumen_reporte_valor_seguro(cliente_id))
