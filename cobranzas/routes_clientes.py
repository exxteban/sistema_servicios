from flask import Blueprint, abort, flash, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.models import Configuracion
from cobranzas import CLAVE_COBRANZAS_ACTIVO, CLAVE_VENTAS_CREDITO_ACTIVO
from cobranzas.services import obtener_detalle_cliente_cobranzas, obtener_resumen_credito_cliente


cobranzas_clientes_bp = Blueprint(
    'cobranzas_clientes',
    __name__,
    template_folder='templates',
)


def _resolver_denegacion():
    if not Configuracion.obtener_bool(CLAVE_COBRANZAS_ACTIVO, default=False):
        flash('El modulo de cobranzas esta desactivado.', 'warning')
        return redirect(url_for('main.dashboard'))
    if current_user.es_admin() or current_user.tiene_permiso('ver_cobranzas'):
        return None
    flash('No tienes permisos para acceder a cobranzas.', 'danger')
    return redirect(url_for('main.dashboard'))


def _resolver_denegacion_api_resumen():
    cobranzas_activas = Configuracion.obtener_bool(CLAVE_COBRANZAS_ACTIVO, default=False)
    ventas_credito_activas = Configuracion.obtener_bool(CLAVE_VENTAS_CREDITO_ACTIVO, default=False)
    if not (cobranzas_activas or ventas_credito_activas):
        return jsonify({'error': 'forbidden', 'mensaje': 'Credito y cobranzas estan desactivados.'}), 403
    if (
        current_user.es_admin()
        or current_user.tiene_permiso('crear_venta')
        or current_user.tiene_permiso('venta_credito')
        or current_user.tiene_permiso('ver_cobranzas')
    ):
        return None
    return jsonify({'error': 'forbidden', 'mensaje': 'No tienes permisos para consultar deuda de clientes.'}), 403


@cobranzas_clientes_bp.route('/clientes/<int:id_cliente>')
@login_required
def detalle_cliente(id_cliente: int):
    denegacion = _resolver_denegacion()
    if denegacion:
        return denegacion

    detalle = obtener_detalle_cliente_cobranzas(int(id_cliente))
    if detalle is None:
        abort(404)
    return render_template('cobranzas/cliente.html', detalle=detalle)


@cobranzas_clientes_bp.route('/api/clientes/<int:id_cliente>/resumen')
@login_required
def resumen_cliente(id_cliente: int):
    denegacion = _resolver_denegacion_api_resumen()
    if denegacion:
        return denegacion

    resumen = obtener_resumen_credito_cliente(int(id_cliente))
    if resumen is None:
        return jsonify({'error': 'not_found', 'mensaje': 'Cliente no encontrado.'}), 404

    puede_abrir_cobranzas = bool(
        Configuracion.obtener_bool(CLAVE_COBRANZAS_ACTIVO, default=False)
        and (
            current_user.es_admin()
            or current_user.tiene_permiso('ver_cobranzas')
            or current_user.tiene_permiso('registrar_cobro_credito')
        )
    )
    url_cliente = url_for('cobranzas_clientes.detalle_cliente', id_cliente=int(id_cliente)) if puede_abrir_cobranzas else None
    cuenta_prioritaria_id = resumen.get('cuenta_prioritaria_id')
    url_cobrar = (
        url_for('cobranzas_cuentas.detalle_cuenta', id_cuenta=int(cuenta_prioritaria_id))
        if (puede_abrir_cobranzas and cuenta_prioritaria_id)
        else url_cliente
    )
    return jsonify(
        {
            'success': True,
            'cliente_id': resumen['cliente_id'],
            'saldo_total': resumen['saldo_total'],
            'cuentas_abiertas': resumen['cuentas_abiertas'],
            'cuentas_vencidas': resumen['cuentas_vencidas'],
            'limite_credito': resumen['limite_credito'],
            'credito_disponible': resumen['credito_disponible'],
            'tiene_deuda': resumen['tiene_deuda'],
            'cuenta_prioritaria_id': cuenta_prioritaria_id,
            'url_cliente': url_cliente,
            'url_cobrar': url_cobrar,
        }
    )
