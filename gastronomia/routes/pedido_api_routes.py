"""API de pedidos para POS gastronomico."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.pedido_service import (
    cambiar_estado_pedido,
    crear_pedido,
    enviar_pedido_cocina,
    listar_pedidos,
    obtener_pedido,
)
from gastronomia.services.permisos import (
    PERMISO_CAJA,
    PERMISO_COCINA,
    PERMISO_POS,
    PERMISO_SALON,
    requiere_permiso_gastronomia,
)


gastronomia_pedidos_api_bp = Blueprint('gastronomia_pedidos_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return cliente_id, None


def _payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


@gastronomia_pedidos_api_bp.route('/pedidos', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_CAJA, PERMISO_COCINA, PERMISO_SALON)
def pedidos():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    estados = [estado.strip() for estado in request.args.getlist('estado') if estado.strip()]
    if not estados and request.args.get('estados'):
        estados = [estado.strip() for estado in request.args.get('estados').split(',') if estado.strip()]
    items = listar_pedidos(cliente_id, estados=estados)
    return jsonify({'ok': True, 'pedidos': [pedido.to_dict() for pedido in items]})


@gastronomia_pedidos_api_bp.route('/pedidos', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def crear():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = crear_pedido(cliente_id, current_user.id_usuario, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': pedido.to_dict()}), 201


@gastronomia_pedidos_api_bp.route('/pedidos/<int:pedido_id>', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_CAJA, PERMISO_COCINA, PERMISO_SALON)
def detalle(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    pedido = obtener_pedido(cliente_id, pedido_id)
    if not pedido:
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'ok': True, 'pedido': pedido.to_dict()})


@gastronomia_pedidos_api_bp.route('/pedidos/<int:pedido_id>/enviar-cocina', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def enviar_cocina(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = enviar_pedido_cocina(cliente_id, pedido_id)
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': pedido.to_dict()})


@gastronomia_pedidos_api_bp.route('/pedidos/<int:pedido_id>/estado', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_COCINA, PERMISO_CAJA)
def estado(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = cambiar_estado_pedido(cliente_id, pedido_id, _payload().get('estado'))
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': pedido.to_dict()})
