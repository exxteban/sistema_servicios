"""API para pantalla TV de menu gastronomico."""
from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.menu_tv_service import (
    actualizar_config_tv,
    obtener_o_preparar_config_tv,
    obtener_payload_publico,
    serializar_config_tv,
)
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia


gastronomia_menu_tv_api_bp = Blueprint('gastronomia_menu_tv_api', __name__)


def _payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


@gastronomia_menu_tv_api_bp.route('/menu-tv/config', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def menu_tv_config():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return jsonify({'error': 'gastronomia_no_activa'}), 403
    config = obtener_o_preparar_config_tv(cliente_id)
    if not config:
        return jsonify({'error': 'not_found'}), 404
    data = serializar_config_tv(config)
    return jsonify({'ok': True, 'config': data, 'public_url': _public_url(data['slug'])})


@gastronomia_menu_tv_api_bp.route('/menu-tv/config', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def actualizar_menu_tv_config():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return jsonify({'error': 'gastronomia_no_activa'}), 403
    try:
        config = actualizar_config_tv(cliente_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    data = serializar_config_tv(config)
    return jsonify({'ok': True, 'config': data, 'public_url': _public_url(data['slug'])})


@gastronomia_menu_tv_api_bp.route('/public/menu-tv/<slug>', methods=['GET'])
def menu_tv_public_api(slug):
    payload = obtener_payload_publico(slug)
    if payload is None:
        return jsonify({'error': 'not_found'}), 404
    return jsonify(payload)


def _public_url(slug: str) -> str:
    return url_for('gastronomia.menu_tv_publico', slug=slug)
