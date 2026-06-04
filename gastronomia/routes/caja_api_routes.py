"""API de caja para Gastronomia."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.caja_service import cobrar_pedido, listar_pedidos_caja
from gastronomia.services.delivery_privacy import (
    ocultar_localizacion_eventos,
    ocultar_localizacion_pedido,
    ocultar_localizacion_pedidos,
)
from gastronomia.services.pedido_service import listar_eventos_pedido, obtener_ultimo_evento_id, serializar_pedidos
from gastronomia.services.permisos import PERMISO_CAJA, requiere_permiso_gastronomia


gastronomia_caja_api_bp = Blueprint('gastronomia_caja_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return cliente_id, None


def _payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


@gastronomia_caja_api_bp.route('/caja/pedidos', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_CAJA)
def caja_pedidos():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    pedidos = listar_pedidos_caja(cliente_id)
    return jsonify({
        'ok': True,
        'pedidos': ocultar_localizacion_pedidos(serializar_pedidos(pedidos), current_user),
        'ultimo_evento_id': obtener_ultimo_evento_id(cliente_id),
    })


@gastronomia_caja_api_bp.route('/caja/eventos', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_CAJA)
def caja_eventos():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    despues_de = request.args.get('after', 0, type=int)
    eventos = listar_eventos_pedido(cliente_id, despues_de=despues_de)
    return jsonify({
        'ok': True,
        'eventos': ocultar_localizacion_eventos([evento.to_dict() for evento in eventos], current_user),
        'ultimo_evento_id': obtener_ultimo_evento_id(cliente_id),
    })


@gastronomia_caja_api_bp.route('/caja/pedidos/<int:pedido_id>/cobrar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_CAJA)
def caja_cobrar(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = cobrar_pedido(cliente_id, current_user.id_usuario, pedido_id, _payload())
    except ValueError as exc:
        if str(exc) == 'Pedido no encontrado.':
            return jsonify({'error': 'not_found'}), 404
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': ocultar_localizacion_pedido(pedido.to_dict(), current_user)})
