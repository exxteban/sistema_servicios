"""API para armar combos con productos del menu gastronomico."""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.menu_combo_service import crear_combo
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia


gastronomia_menu_combo_api_bp = Blueprint('gastronomia_menu_combo_api', __name__)


@gastronomia_menu_combo_api_bp.route('/combos', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def crear():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return jsonify({'error': 'gastronomia_no_activa'}), 403
    try:
        resultado = crear_combo(cliente_id, request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, **resultado}), 201
