"""
Blueprint CRM - WhatsApp CRM Module
Montado en /crm dentro del sistema principal.
"""
import os

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from app.services.system_modules import CLAVE_MODULO_CRM, system_module_enabled

crm_bp = Blueprint('crm', __name__)


def _modulo_crm_activo() -> bool:
    return system_module_enabled(CLAVE_MODULO_CRM, default=True)


def _min_nivel_bandeja_jefe() -> int:
    try:
        return int(os.environ.get('CRM_BANDEJA_JEFE_MIN_NIVEL', '100'))
    except (TypeError, ValueError):
        return 100


def usuario_puede_ver_bandeja_jefe(usuario) -> bool:
    if not usuario or not getattr(usuario, 'is_authenticated', False):
        return False
    if usuario.es_admin():
        return True
    nivel = getattr(getattr(usuario, 'rol', None), 'nivel_jerarquia', 0) or 0
    return int(nivel) >= _min_nivel_bandeja_jefe()


@crm_bp.app_context_processor
def _inject_crm_acl():
    return {
        'crm_puede_ver_bandeja_jefe': usuario_puede_ver_bandeja_jefe(current_user),
    }

@crm_bp.before_request
def _require_crm_whatsapp_permiso():
    if not current_user.is_authenticated:
        return None
    if not _modulo_crm_activo():
        mensaje = 'El modulo CRM esta desactivado.'
        wants_json = (
            request.path.startswith('/crm/api/')
            or request.is_json
            or bool(request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html)
        )
        if wants_json:
            return jsonify({'error': 'Modulo desactivado', 'mensaje': mensaje, 'modulo': 'crm'}), 403
        flash(mensaje, 'warning')
        return redirect(url_for('main.dashboard'))
    if current_user.tiene_permiso('crm_whatsapp'):
        return None

    modo_demo = bool(getattr(current_user, 'modo_demo', False))
    mensaje = 'Modo demo: esta acción está deshabilitada' if modo_demo else 'No tienes permiso para acceder a CRM WhatsApp'
    wants_json = (
        request.path.startswith('/crm/api/')
        or request.is_json
        or bool(request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html)
    )
    if wants_json:
        return jsonify({'error': 'Sin permisos', 'mensaje': mensaje, 'permiso_requerido': 'crm_whatsapp', 'modo_demo': modo_demo}), 403
    return render_template('errores/403.html'), 403

from app.routes.crm import bandeja, contactos, asesor, admin, monitor  # noqa: E402, F401
