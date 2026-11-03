"""Panel de salud de uso, solo para el usuario root de la instalacion (BI-05)."""
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services.ia_backoffice.security import es_usuario_root
from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.bi.interruptor import bi_activo, cambiar_bi_activo
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
    return render_template('gastronomia/bi_salud_uso.html', salud=resumen_salud_uso(cliente_id), bi_activo=bi_activo(cliente_id))


@gastronomia_bp.route('/bi/activo', methods=['POST'])
@login_required
def bi_cambiar_activo():
    if not es_usuario_root(current_user):
        abort(403)
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    activo = request.form.get('activo') == '1'
    cambiar_bi_activo(cliente_id, activo)
    flash('Experiencia comercial del BI activada.' if activo else 'Experiencia comercial del BI desactivada. No se borró ningún dato.', 'success')
    return redirect(url_for('gastronomia.bi_salud_uso'))
