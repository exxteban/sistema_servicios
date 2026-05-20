from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import Configuracion
from cobranzas import CLAVE_COBRANZAS_ACTIVO
from cobranzas.services import construir_resumen_cobranzas, listar_cuentas_por_cobrar


cobranzas_bp = Blueprint(
    'cobranzas',
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


@cobranzas_bp.route('/')
@login_required
def index():
    denegacion = _resolver_denegacion()
    if denegacion:
        return denegacion

    listado = listar_cuentas_por_cobrar(
        page=max(request.args.get('page', 1, type=int), 1),
        per_page=20,
        filtro_estado=(request.args.get('estado') or 'abiertas'),
        busqueda=(request.args.get('q') or ''),
    )
    return render_template(
        'cobranzas/index.html',
        resumen=construir_resumen_cobranzas(limit_cuentas=0),
        listado=listado,
    )
