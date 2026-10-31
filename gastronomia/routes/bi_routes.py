"""Accion del tab Crecer: confirmar los pasos de activacion que no se detectan solos."""
from flask import abort, flash, redirect, request, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.bi.activacion import PASOS_MANUALES, marcar_paso_manual
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia


@gastronomia_bp.route('/bi/activacion/<paso>', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def bi_activacion_marcar(paso: str):
    if paso not in PASOS_MANUALES:
        abort(404)
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    marcar_paso_manual(cliente_id, paso, request.form.get('hecho') == '1')
    return redirect(url_for('inteligencia.dashboard', vista='gastronomia'))
