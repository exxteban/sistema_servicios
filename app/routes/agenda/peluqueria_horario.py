from datetime import datetime

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.routes.agenda import agenda_bp
from app.routes.agenda.peluqueria import _obtener_profesionales_disponibles, _parse_positive_int
from app.services.peluqueria_recordatorios import (
    HORAS_PERMITIDAS,
    guardar_config_recordatorios,
    obtener_config_recordatorios,
    whatsapp_configurado,
)
from app.services.peluqueria_horario import (
    INTERVALOS_PERMITIDOS,
    guardar_horario_peluqueria,
    obtener_horario_peluqueria,
    rangos_ocupados_peluqueria,
)


@agenda_bp.route('/api/peluqueria/ocupados', methods=['GET'])
@login_required
def api_peluqueria_ocupados():
    profesional_id = _parse_positive_int(request.args.get('profesional_id'))
    try:
        fecha = datetime.strptime((request.args.get('fecha') or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Fecha inválida'}), 400
    visibles = {int(usuario.id_usuario) for usuario in _obtener_profesionales_disponibles()}
    if not profesional_id or profesional_id not in visibles:
        return jsonify({'error': 'Profesional no disponible'}), 404
    return jsonify({
        'profesional_id': profesional_id,
        'fecha': fecha.isoformat(),
        'ocupados': rangos_ocupados_peluqueria(profesional_id=profesional_id, fecha=fecha),
    })


@agenda_bp.route('/turnos/peluqueria/horario', methods=['GET', 'POST'])
@login_required
def horario_peluqueria():
    if not current_user.es_admin():
        flash('Solo un administrador puede cambiar el horario del local.', 'danger')
        return redirect(url_for('main.dashboard'))

    horario = obtener_horario_peluqueria()
    if request.method == 'POST' and request.form.get('seccion') == 'recordatorios':
        error = guardar_config_recordatorios(request.form.get('horas_antes'), request.form.get('template'))
        flash(error or 'Recordatorios guardados.', 'warning' if error else 'success')
        return redirect(url_for('agenda.horario_peluqueria'))
    if request.method == 'POST':
        _, error = guardar_horario_peluqueria(
            request.form.get('apertura'),
            request.form.get('cierre'),
            request.form.get('intervalo'),
        )
        if error:
            flash(error, 'warning')
            horario = {
                'apertura': request.form.get('apertura') or horario['apertura'],
                'cierre': request.form.get('cierre') or horario['cierre'],
                'intervalo': _parse_positive_int(request.form.get('intervalo')) or horario['intervalo'],
            }
        else:
            flash('Horario del local guardado.', 'success')
            return redirect(url_for('agenda.horario_peluqueria'))

    return render_template(
        'agenda/peluqueria_horario.html',
        horario=horario,
        intervalos=INTERVALOS_PERMITIDOS,
        recordatorios=obtener_config_recordatorios(),
        horas_recordatorio=HORAS_PERMITIDAS,
        whatsapp_configurado=whatsapp_configurado(),
    )
