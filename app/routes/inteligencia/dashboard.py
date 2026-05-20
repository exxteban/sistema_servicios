from flask import flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.routes.inteligencia import inteligencia_bp
from app.services.inteligencia import obtener_panel_inteligencia_comercial
from app.services.inteligencia.periodos import normalizar_periodo
from app.utils.bi_context import construir_resumen_dashboard_desde_panel, enriquecer_panel_productos_inteligencia

VISTAS_INTELIGENCIA_VALIDAS = {'resumen', 'comercial', 'operacion'}


def _puede_ver_inteligencia() -> bool:
    return current_user.es_admin() or current_user.tiene_permiso('ver_reportes')


@inteligencia_bp.route('/inteligencia')
@login_required
def dashboard():
    if not _puede_ver_inteligencia():
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para acceder al Centro de Inteligencia Comercial.', 'danger')
        return redirect(url_for('main.dashboard'))

    vista_activa = request.args.get('vista', 'resumen')
    if vista_activa not in VISTAS_INTELIGENCIA_VALIDAS:
        vista_activa = 'resumen'
    periodo_activo = normalizar_periodo(request.args.get('periodo'))

    panel = obtener_panel_inteligencia_comercial(
        id_cliente_tienda=getattr(current_user, 'id_cliente', None),
        periodo=periodo_activo,
    )
    enriquecer_panel_productos_inteligencia(panel, current_user)
    g.inteligencia_resumen_override = construir_resumen_dashboard_desde_panel(panel)
    return render_template(
        'inteligencia/dashboard.html',
        panel=panel,
        vista_activa=vista_activa,
    )
