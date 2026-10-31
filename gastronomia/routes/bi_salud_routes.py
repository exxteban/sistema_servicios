"""Panel de salud de uso, solo para el usuario root de la instalacion (BI-05)."""
from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.services.ia_backoffice.security import es_usuario_root
from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.bi.salud_uso import resumen_salud_uso


@gastronomia_bp.route('/bi/salud-uso')
@login_required
def bi_salud_uso():
    # Va antes que cualquier dato: ni el menu ni una URL directa muestran el panel a otros usuarios.
    if not es_usuario_root(current_user):
        abort(403)
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    return render_template('gastronomia/bi_salud_uso.html', salud=resumen_salud_uso(cliente_id))
