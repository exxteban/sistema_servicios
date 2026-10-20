from datetime import datetime, timedelta

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.routes.agenda import agenda_bp
from app.routes.agenda.visibilidad import query_usuarios_agenda_visibles
from app.services.peluqueria_comisiones import calcular_comisiones
from app.services.peluqueria_profesionales import filtrar_query_profesionales
from app.utils.helpers import today_local


def puede_ver_comisiones(usuario) -> bool:
    return usuario.es_admin() or usuario.tiene_permiso('ver_reporte_ventas')


def _parse_fecha(valor):
    try:
        return datetime.strptime((valor or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _rangos_rapidos(hoy):
    inicio_mes = hoy.replace(day=1)
    fin_mes_anterior = inicio_mes - timedelta(days=1)
    return [
        ('Hoy', hoy, hoy),
        ('Esta semana', hoy - timedelta(days=hoy.weekday()), hoy),
        ('Este mes', inicio_mes, hoy),
        ('Mes anterior', fin_mes_anterior.replace(day=1), fin_mes_anterior),
    ]


@agenda_bp.route('/peluqueria/comisiones', methods=['GET'])
@login_required
def comisiones_peluqueria():
    if not puede_ver_comisiones(current_user):
        flash('No tienes permiso para ver las comisiones.', 'danger')
        return redirect(url_for('main.dashboard'))

    hoy = today_local()
    desde = _parse_fecha(request.args.get('desde')) or hoy
    hasta = _parse_fecha(request.args.get('hasta')) or desde
    if hasta < desde:
        desde, hasta = hasta, desde
    resumen = calcular_comisiones(
        desde,
        hasta,
        profesionales=filtrar_query_profesionales(query_usuarios_agenda_visibles()).all(),
    )
    return render_template(
        'agenda/peluqueria_comisiones.html',
        resumen=resumen,
        rangos=[(etiqueta, inicio.isoformat(), fin.isoformat()) for etiqueta, inicio, fin in _rangos_rapidos(hoy)],
        puede_editar_porcentajes=current_user.tiene_permiso('gestionar_usuarios') or current_user.es_admin(),
    )
