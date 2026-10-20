from datetime import datetime, timedelta

from flask import render_template, request
from flask_login import current_user, login_required

from app.routes.agenda import agenda_bp
from app.routes.agenda.peluqueria import _obtener_profesionales_disponibles, _query_turnos_peluqueria_visibles
from app.services.peluqueria_agenda_dia import construir_agenda_dia
from app.utils.helpers import now_local, today_local


def _parse_fecha(valor):
    try:
        return datetime.strptime((valor or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


@agenda_bp.route('/peluqueria/dia', methods=['GET'])
@login_required
def agenda_dia_peluqueria():
    ahora = now_local()
    hoy = today_local()
    dia = _parse_fecha(request.args.get('fecha')) or hoy
    agenda = construir_agenda_dia(
        dia=dia,
        profesionales=_obtener_profesionales_disponibles(),
        query_turnos=_query_turnos_peluqueria_visibles(),
    )
    return render_template(
        'agenda/peluqueria_agenda_dia.html',
        agenda=agenda,
        es_hoy=(dia == hoy),
        ahora_min=ahora.hour * 60 + ahora.minute,
        dia_anterior=(dia - timedelta(days=1)).isoformat(),
        dia_siguiente=(dia + timedelta(days=1)).isoformat(),
        puede_crear_turno=current_user.tiene_permiso('agenda_crear'),
        es_pasado=(dia < hoy),
    )
