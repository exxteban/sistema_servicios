"""Tablero de encargos (pasteleria / cafeteria)."""
from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.encargo_service import encargos_habilitados
from gastronomia.services.pasteleria_flags import parametros_encargos
from gastronomia.services.permisos import PERMISO_CAJA, PERMISO_POS, requiere_permiso_gastronomia, tiene_permiso_gastronomia


@gastronomia_bp.route('/encargos')
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def encargos():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    if not encargos_habilitados(cliente_id):
        flash('Los encargos no estan habilitados para este local.', 'warning')
        return redirect(url_for('gastronomia.dashboard'))
    return render_template(
        'gastronomia/encargos.html',
        parametros=parametros_encargos(cliente_id),
        puede_cobrar=tiene_permiso_gastronomia(PERMISO_CAJA),
    )
