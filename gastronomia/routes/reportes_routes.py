"""Pantalla de reportes gastronomicos."""
from datetime import timedelta

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.utils.helpers import parse_iso_date, today_local
from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.permisos import PERMISO_REPORTES, requiere_permiso_gastronomia


@gastronomia_bp.route('/reportes')
@login_required
@requiere_permiso_gastronomia(PERMISO_REPORTES)
def reportes():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    # Accesos directos (inicio, contabilidad) abren el reporte en "Cuanto ganamos" con un rango dado.
    desde = parse_iso_date(request.args.get('desde'))
    hasta = parse_iso_date(request.args.get('hasta')) or desde
    rango = request.args.get('rango')
    if not desde and rango in ('hoy', '7', 'mes'):
        hasta = today_local()
        desde = {'hoy': hasta, '7': hasta - timedelta(days=6), 'mes': hasta.replace(day=1)}[rango]
    return render_template(
        'gastronomia/reportes.html',
        inicio_desde=desde.isoformat() if desde else '',
        inicio_hasta=hasta.isoformat() if hasta else '',
        inicio_rango=rango if rango in ('hoy', '7', 'mes') else '',
        inicio_ver=request.args.get('ver') == 'ganancia',
    )
