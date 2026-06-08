"""API de pedidos para POS gastronomico."""
from flask import Blueprint, jsonify, request, url_for
from flask_login import current_user, login_required

from app.models import SesionCaja
from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.delivery_privacy import ocultar_localizacion_pedido, ocultar_localizacion_pedidos
from gastronomia.services.pedido_service import (
    actualizar_pedido_abierto,
    cambiar_estado_pedido,
    crear_pedido,
    enviar_pedido_cocina,
    listar_pedidos,
    obtener_pedido,
    serializar_pedidos,
)
from gastronomia.services.tienda_pedido_service import (
    confirmar_pedido_tienda,
    listar_pedidos_tienda,
    serializar_pedidos_tienda,
)
from gastronomia.services.venta_integration_service import crear_cola_cobro_central_desde_pedido
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
    tipo_pedido = request.args.get('tipo_pedido') or request.args.get('tipo')
    items = listar_pedidos(cliente_id, estados=estados, tipo_pedido=tipo_pedido)
    return jsonify({'ok': True, 'pedidos': ocultar_localizacion_pedidos(serializar_pedidos(items), current_user)})


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
    return jsonify({'ok': True, 'pedido': _pedido_data(pedido)}), 201


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
    return jsonify({'ok': True, 'pedido': _pedido_data(pedido)})


@gastronomia_pedidos_api_bp.route('/pedidos/<int:pedido_id>', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def actualizar(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = actualizar_pedido_abierto(cliente_id, pedido_id, _payload())
    except ValueError as exc:
        if str(exc) == 'Pedido no encontrado.':
            return jsonify({'error': 'not_found'}), 404
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': _pedido_data(pedido)})


@gastronomia_pedidos_api_bp.route('/pedidos/<int:pedido_id>/enviar-cocina', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_CAJA, PERMISO_COCINA)
def enviar_cocina(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = enviar_pedido_cocina(cliente_id, pedido_id)
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': _pedido_data(pedido)})


@gastronomia_pedidos_api_bp.route('/tienda/pedidos', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_CAJA)
def pedidos_tienda_listar():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    solo_pendientes = (request.args.get('pendientes', '1') or '1').strip() != '0'
    pedidos = listar_pedidos_tienda(cliente_id, solo_pendientes=solo_pendientes)
    return jsonify({'ok': True, 'pedidos': serializar_pedidos_tienda(pedidos)})


@gastronomia_pedidos_api_bp.route('/tienda/pedidos/<int:pedido_id>/confirmar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_CAJA)
def pedidos_tienda_confirmar(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = confirmar_pedido_tienda(cliente_id, pedido_id)
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': _pedido_data(pedido)})


@gastronomia_pedidos_api_bp.route('/pedidos/<int:pedido_id>/cobro-avanzado', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_CAJA)
def cobro_avanzado(pedido_id):
    if not (current_user.es_admin() or current_user.tiene_permiso('crear_venta')):
        return jsonify({
            'error': 'Sin permisos',
            'mensaje': 'Se requiere permiso de ventas para usar el cobro avanzado.',
        }), 403
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    pedido = obtener_pedido(cliente_id, pedido_id)
    if not pedido:
        return jsonify({'error': 'not_found'}), 404
    sesion = SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta',
    ).first()
    if not sesion:
        return jsonify({
            'error': 'caja_no_abierta',
            'mensaje': 'Debe abrir una caja antes de cobrar el pedido.',
            'redirect_url': url_for('caja.abrir'),
        }), 400
    try:
        cola = crear_cola_cobro_central_desde_pedido(
            pedido,
            current_user.id_usuario,
            enviar_cocina=bool(_payload().get('enviar_cocina', True)),
        )
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({
        'ok': True,
        'cola_id': int(cola.id),
        'checkout_url': url_for('ventas.pos', cola_id=cola.id),
    })


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
    return jsonify({'ok': True, 'pedido': _pedido_data(pedido)})


def _pedido_data(pedido):
    return ocultar_localizacion_pedido(pedido.to_dict(), current_user)
