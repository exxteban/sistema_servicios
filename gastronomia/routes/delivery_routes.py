"""Panel operativo de delivery gastronomico."""
from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from app.models import Usuario

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.permisos import (
    PERMISO_CAJA,
    PERMISO_COCINA,
    PERMISO_DELIVERY,
    PERMISO_POS,
    requiere_permiso_gastronomia,
    tiene_permiso_gastronomia,
)


@gastronomia_bp.route('/delivery')
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_CAJA, PERMISO_COCINA)
def delivery():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    usuarios_delivery = (
        Usuario.query
        .filter(Usuario.id_cliente == int(cliente_id), Usuario.activo.is_(True))
        .order_by(Usuario.nombre_completo.asc(), Usuario.username.asc())
        .all()
    )
    return render_template(
        'gastronomia/delivery.html',
        usuarios_delivery=usuarios_delivery,
        puede_ver_ruta=tiene_permiso_gastronomia(PERMISO_DELIVERY),
    )


@gastronomia_bp.route('/delivery/ruta')
@login_required
@requiere_permiso_gastronomia(PERMISO_DELIVERY)
def delivery_ruta():
    if not cliente_id_actual_gastronomia():
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    return render_template('gastronomia/delivery_ruta.html')
