"""Pantalla de produccion diaria, porciones y merma (pasteleria / cafeteria)."""
from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from gastronomia.produccion_models import MOTIVO_FALTANTE, MOTIVOS_MERMA
from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.permisos import (
    PERMISO_COCINA,
    PERMISO_MENU,
    PERMISO_POS,
    PERMISO_REPORTES,
    requiere_permiso_gastronomia,
    tiene_permiso_gastronomia,
)
from gastronomia.services.produccion_service import produccion_habilitada


@gastronomia_bp.route('/produccion')
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_COCINA)
def produccion():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    if not produccion_habilitada(cliente_id):
        flash('La produccion diaria no esta habilitada para este local.', 'warning')
        return redirect(url_for('gastronomia.dashboard'))
    return render_template(
        'gastronomia/produccion.html',
        motivos={k: v for k, v in MOTIVOS_MERMA.items() if k != MOTIVO_FALTANTE},
        puede_configurar=tiene_permiso_gastronomia(PERMISO_MENU),
        puede_ver_reporte=tiene_permiso_gastronomia(PERMISO_REPORTES, PERMISO_MENU),
    )
