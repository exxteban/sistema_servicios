from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import Configuracion, MetodoPago, SesionCaja
from cobranzas import CLAVE_COBRANZAS_ACTIVO
from cobranzas.services.cobranza_service import _metodo_pago_es_credito_tienda
from cobranzas.services import obtener_detalle_cuenta


cobranzas_cuentas_bp = Blueprint(
    'cobranzas_cuentas',
    __name__,
    template_folder='templates',
)


def _resolver_denegacion(*permisos_extra):
    if not Configuracion.obtener_bool(CLAVE_COBRANZAS_ACTIVO, default=False):
        flash('El modulo de cobranzas esta desactivado.', 'warning')
        return redirect(url_for('main.dashboard'))
    if current_user.es_admin() or current_user.tiene_permiso('ver_cobranzas'):
        return None
    if any(current_user.tiene_permiso(permiso) for permiso in permisos_extra if permiso):
        return None
    flash('No tienes permisos para acceder a cobranzas.', 'danger')
    return redirect(url_for('main.dashboard'))


@cobranzas_cuentas_bp.route('/cuentas')
@login_required
def listar_cuentas():
    denegacion = _resolver_denegacion()
    if denegacion:
        return denegacion

    return redirect(
        url_for(
            'cobranzas.index',
            page=max(request.args.get('page', 1, type=int), 1),
            estado=(request.args.get('estado') or 'abiertas'),
            q=(request.args.get('q') or ''),
        )
    )


@cobranzas_cuentas_bp.route('/cuentas/<int:id_cuenta>')
@login_required
def detalle_cuenta(id_cuenta: int):
    denegacion = _resolver_denegacion('registrar_cobro_credito')
    if denegacion:
        return denegacion

    detalle = obtener_detalle_cuenta(int(id_cuenta))
    if detalle is None:
        abort(404)
    metodos_pago = MetodoPago.query.filter_by(activo=True).order_by(MetodoPago.orden_display.asc(), MetodoPago.id_metodo_pago.asc()).all()
    metodos_pago = [metodo for metodo in metodos_pago if not _metodo_pago_es_credito_tienda(metodo)]
    sesion_activa = SesionCaja.query.filter_by(id_usuario=current_user.id_usuario, estado='abierta').first()
    return render_template(
        'cobranzas/cuenta.html',
        detalle=detalle,
        metodos_pago=metodos_pago,
        sesion_activa=sesion_activa,
    )
