from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user

agenda_bp = Blueprint('agenda', __name__)


@agenda_bp.before_request
def _require_agenda_acceso_permiso():
    if not current_user.is_authenticated:
        return None
    if current_user.tiene_permiso('agenda_acceso'):
        return None

    modo_demo = bool(getattr(current_user, 'modo_demo', False))
    mensaje = 'Modo demo: esta acción está deshabilitada' if modo_demo else 'No tienes permiso para acceder a Agenda'
    wants_json = (
        request.path.startswith('/agenda/api/')
        or request.is_json
        or bool(request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html)
    )
    if wants_json:
        return jsonify({'error': 'Sin permisos', 'mensaje': mensaje, 'permiso_requerido': 'agenda_acceso', 'modo_demo': modo_demo}), 403
    return render_template('errores/403.html'), 403


from app.routes.agenda import actividades, dashboard, peluqueria  # noqa: E402, F401
