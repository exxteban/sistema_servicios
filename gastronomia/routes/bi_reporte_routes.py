"""Configuracion de comisiones del reporte de valor (BI-03)."""
from flask import flash, redirect, request, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.bi.comision import guardar_porcentajes
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia


@gastronomia_bp.route('/bi/comision', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def bi_comision_configuracion():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    try:
        guardar_porcentajes(cliente_id, request.form)
    except ValueError as error:
        flash(str(error), 'warning')
    else:
        flash('Comisiones guardadas.', 'success')
    return redirect(url_for('inteligencia.dashboard', vista='gastronomia'))
