"""API de cocina/KDS para Gastronomia."""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.pedido_service import (
    cambiar_estado_pedido,
    listar_eventos_pedido,
    listar_pedidos_cocina,
    obtener_ultimo_evento_id,
    serializar_pedidos,
)
from gastronomia.services.permisos import PERMISO_COCINA, requiere_permiso_gastronomia


gastronomia_cocina_api_bp = Blueprint('gastronomia_cocina_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return cliente_id, None


@gastronomia_cocina_api_bp.route('/cocina/pedidos', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_COCINA)
def cocina_pedidos():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    pedidos = listar_pedidos_cocina(cliente_id)
    return jsonify({
        'ok': True,
        'pedidos': serializar_pedidos(pedidos),
        'ultimo_evento_id': obtener_ultimo_evento_id(cliente_id),
    })


@gastronomia_cocina_api_bp.route('/cocina/eventos', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_COCINA)
def cocina_eventos():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    despues_de = request.args.get('after', 0, type=int)
    eventos = listar_eventos_pedido(cliente_id, despues_de=despues_de)
    return jsonify({
        'ok': True,
        'eventos': [evento.to_dict() for evento in eventos],
        'ultimo_evento_id': obtener_ultimo_evento_id(cliente_id),
    })


@gastronomia_cocina_api_bp.route('/cocina/pedidos/<int:pedido_id>/tomar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_COCINA)
def cocina_tomar(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = cambiar_estado_pedido(cliente_id, pedido_id, 'preparando')
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': serializar_pedidos([pedido])[0]})


@gastronomia_cocina_api_bp.route('/cocina/pedidos/<int:pedido_id>/listo', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_COCINA)
def cocina_listo(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = cambiar_estado_pedido(cliente_id, pedido_id, 'listo')
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': serializar_pedidos([pedido])[0]})


@gastronomia_cocina_api_bp.route('/cocina/pedidos/<int:pedido_id>/entregar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_COCINA)
def cocina_entregar(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = cambiar_estado_pedido(cliente_id, pedido_id, 'entregado')
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': serializar_pedidos([pedido])[0]})
