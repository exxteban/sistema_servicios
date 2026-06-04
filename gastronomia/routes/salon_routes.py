"""Pantalla de salon gastronomico."""
from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.permisos import (
    PERMISO_CAJA,
    PERMISO_POS,
    PERMISO_SALON,
    requiere_permiso_gastronomia,
    tiene_permiso_gastronomia,
)


@gastronomia_bp.route('/salon')
@login_required
@requiere_permiso_gastronomia(PERMISO_SALON)
def salon():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    return render_template(
        'gastronomia/salon.html',
        puede_cobrar=tiene_permiso_gastronomia(PERMISO_CAJA),
        puede_editar_pedido=tiene_permiso_gastronomia(PERMISO_POS),
    )


@gastronomia_bp.route('/salon/configuracion')
@login_required
@requiere_permiso_gastronomia(PERMISO_SALON)
def salon_config():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    return render_template('gastronomia/salon_config.html')
