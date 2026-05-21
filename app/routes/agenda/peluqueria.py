from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.models import Usuario
from app.routes.agenda import agenda_bp


SERVICIOS_TURNO_PELUQUERIA = (
    {'id': 'corte', 'nombre': 'Corte', 'duracion': 30, 'icono': 'fas fa-cut'},
    {'id': 'barba', 'nombre': 'Barba', 'duracion': 20, 'icono': 'fas fa-user'},
    {'id': 'corte_barba', 'nombre': 'Corte + barba', 'duracion': 45, 'icono': 'fas fa-user-tie'},
    {'id': 'color', 'nombre': 'Color', 'duracion': 90, 'icono': 'fas fa-palette'},
    {'id': 'peinado', 'nombre': 'Peinado', 'duracion': 45, 'icono': 'fas fa-wind'},
    {'id': 'lavado', 'nombre': 'Lavado', 'duracion': 20, 'icono': 'fas fa-shower'},
    {'id': 'otro', 'nombre': 'Otro servicio', 'duracion': 30, 'icono': 'fas fa-plus'},
)

HORARIOS_TURNO_PELUQUERIA = tuple(
    f'{hora:02d}:{minuto:02d}'
    for hora in range(8, 21)
    for minuto in (0, 30)
)


def _puede_asignar_profesional():
    return current_user.es_admin() or current_user.tiene_permiso('agenda_ver_todas')


def _serializar_profesional(usuario):
    return {
        'id': usuario.id_usuario,
        'nombre': usuario.nombre_completo or usuario.username,
        'iniciales': _iniciales_usuario(usuario),
    }


def _iniciales_usuario(usuario):
    nombre = usuario.nombre_completo or usuario.username or 'P'
    partes = [parte[0] for parte in nombre.split() if parte]
    return ''.join(partes[:2]).upper() or 'P'


def _obtener_profesionales_disponibles():
    if not _puede_asignar_profesional():
        return [current_user]
    return Usuario.query.filter_by(activo=True).order_by(Usuario.nombre_completo.asc()).all()


@agenda_bp.route('/turnos/peluqueria/nuevo', methods=['GET'])
@login_required
def nuevo_turno_peluqueria():
    if not current_user.tiene_permiso('agenda_crear'):
        flash('No tienes permiso para crear turnos.', 'danger')
        return redirect(url_for('agenda.lista_actividades'))

    profesionales = [_serializar_profesional(usuario) for usuario in _obtener_profesionales_disponibles()]
    return render_template(
        'agenda/peluqueria_turno_rapido.html',
        profesionales=profesionales,
        servicios=SERVICIOS_TURNO_PELUQUERIA,
        horarios=HORARIOS_TURNO_PELUQUERIA,
        puede_ver_agenda=current_user.tiene_permiso('agenda_acceso'),
    )
