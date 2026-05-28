"""API de mesas y salon para Gastronomia."""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.salon_service import (
    eliminar_mesa,
    guardar_mesa,
    listar_mesas,
    listar_salon,
    mover_pedido_mesa,
    obtener_mesa,
)
from gastronomia.services.permisos import PERMISO_POS, PERMISO_SALON, requiere_permiso_gastronomia


gastronomia_salon_api_bp = Blueprint('gastronomia_salon_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return cliente_id, None


def _payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


@gastronomia_salon_api_bp.route('/salon/estado', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_SALON)
def salon_estado():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    return jsonify({'ok': True, 'mesas': listar_salon(cliente_id)})


@gastronomia_salon_api_bp.route('/salon/mesas', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_SALON, PERMISO_POS)
def mesas():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    incluir_inactivas = request.args.get('inactivas') == '1'
    items = listar_mesas(cliente_id, incluir_inactivas=incluir_inactivas)
    return jsonify({'ok': True, 'mesas': [mesa.to_dict() for mesa in items]})


@gastronomia_salon_api_bp.route('/salon/mesas', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_SALON)
def crear_mesa():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        mesa = guardar_mesa(cliente_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'mesa': mesa.to_dict()}), 201


@gastronomia_salon_api_bp.route('/salon/mesas/<int:mesa_id>', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_SALON)
def actualizar_mesa(mesa_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    mesa = obtener_mesa(cliente_id, mesa_id)
    if not mesa:
        return jsonify({'error': 'not_found'}), 404
    try:
        mesa = guardar_mesa(cliente_id, _payload(), mesa=mesa)
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'mesa': mesa.to_dict()})


@gastronomia_salon_api_bp.route('/salon/mesas/<int:mesa_id>', methods=['DELETE'])
@login_required
@requiere_permiso_gastronomia(PERMISO_SALON)
def borrar_mesa(mesa_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    if not eliminar_mesa(cliente_id, mesa_id):
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'ok': True})


@gastronomia_salon_api_bp.route('/salon/pedidos/<int:pedido_id>/mover', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_SALON)
def mover_pedido(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = mover_pedido_mesa(cliente_id, pedido_id, _payload())
    except ValueError as exc:
        if str(exc) == 'Pedido no encontrado.':
            return jsonify({'error': 'not_found'}), 404
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': pedido.to_dict()})
