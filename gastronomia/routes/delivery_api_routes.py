"""API de repartidores y hoja de ruta delivery."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.delivery_service import (
    actualizar_repartidor,
    actualizar_destino_pedido_delivery,
    asignar_repartidor_pedido,
    crear_repartidor,
    listar_repartidores,
    listar_ruta_operativa,
    listar_ruta_repartidor,
    marcar_pedido_ruta_operativa,
    marcar_pedido_ruta,
    obtener_repartidor_usuario,
    registrar_ubicacion_repartidor,
)
from gastronomia.services.delivery_privacy import (
    ocultar_localizacion_pedidos,
    puede_ver_localizacion_delivery,
)
from gastronomia.services.pedido_service import serializar_pedidos
from gastronomia.services.permisos import (
    PERMISO_CAJA,
    PERMISO_COCINA,
    PERMISO_DELIVERY,
    PERMISO_DELIVERY_GPS,
    PERMISO_POS,
    requiere_permiso_gastronomia,
    tiene_permiso_gastronomia,
)


gastronomia_delivery_api_bp = Blueprint('gastronomia_delivery_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return cliente_id, None


def _payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


@gastronomia_delivery_api_bp.route('/delivery/repartidores', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_CAJA, PERMISO_COCINA)
def repartidores():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    incluir_inactivos = (request.args.get('incluir_inactivos') or '').strip() in {'1', 'true', 'si'}
    items = listar_repartidores(cliente_id, incluir_inactivos=incluir_inactivos)
    return jsonify({'ok': True, 'repartidores': [item.to_dict() for item in items]})


@gastronomia_delivery_api_bp.route('/delivery/repartidores', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_CAJA)
def crear_repartidor_api():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        repartidor = crear_repartidor(cliente_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'repartidor': repartidor.to_dict()}), 201


@gastronomia_delivery_api_bp.route('/delivery/repartidores/<int:repartidor_id>', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_CAJA)
def actualizar_repartidor_api(repartidor_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        repartidor = actualizar_repartidor(cliente_id, repartidor_id, _payload())
    except ValueError as exc:
        status = 404 if str(exc) == 'Repartidor no encontrado.' else 400
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), status
    return jsonify({'ok': True, 'repartidor': repartidor.to_dict()})


@gastronomia_delivery_api_bp.route('/delivery/pedidos/<int:pedido_id>/repartidor', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_POS, PERMISO_CAJA, PERMISO_COCINA)
def asignar_repartidor_api(pedido_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        pedido = asignar_repartidor_pedido(cliente_id, pedido_id, _payload().get('repartidor_id'))
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': _serializar_pedidos_ruta([pedido])[0]})


@gastronomia_delivery_api_bp.route('/delivery/ruta', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_DELIVERY)
def ruta_delivery():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    repartidor = obtener_repartidor_usuario(cliente_id, current_user.id_usuario)
    if repartidor:
        _repartidor, pedidos = listar_ruta_repartidor(cliente_id, current_user.id_usuario)
        return jsonify({
            'ok': True,
            'modo': 'repartidor',
            'repartidor': _repartidor.to_dict(),
            'pedidos': _serializar_pedidos_ruta(pedidos),
        })
    if _puede_ver_ruta_operativa():
        pedidos = listar_ruta_operativa(cliente_id)
        return jsonify({
            'ok': True,
            'modo': 'operativo',
            'repartidor': None,
            'pedidos': _serializar_pedidos_ruta(pedidos),
            'mensaje': 'Vista operativa: pedidos delivery listos o en camino.',
        })
    return jsonify({
        'ok': True,
        'modo': 'sin_repartidor',
        'repartidor': None,
        'pedidos': [],
        'mensaje': 'Este usuario aun no esta vinculado a un repartidor activo.',
    })


@gastronomia_delivery_api_bp.route('/delivery/ruta/pedidos/<int:pedido_id>/salir', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_DELIVERY)
def ruta_salir(pedido_id):
    return _marcar_ruta(pedido_id, 'en_camino')


@gastronomia_delivery_api_bp.route('/delivery/ruta/pedidos/<int:pedido_id>/entregar', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_DELIVERY)
def ruta_entregar(pedido_id):
    return _marcar_ruta(pedido_id, 'entregado')


@gastronomia_delivery_api_bp.route('/delivery/ruta/pedidos/<int:pedido_id>/ubicacion', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_DELIVERY)
def ruta_ubicacion(pedido_id):
    if not tiene_permiso_gastronomia(PERMISO_DELIVERY_GPS):
        return _error_gps_sin_permiso()
    if not puede_ver_localizacion_delivery(current_user):
        return _error_localizacion_restringida()
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        ubicacion = registrar_ubicacion_repartidor(cliente_id, current_user.id_usuario, pedido_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'ubicacion': ubicacion.to_dict()})


@gastronomia_delivery_api_bp.route('/delivery/ruta/pedidos/<int:pedido_id>/destino', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_DELIVERY)
def ruta_destino(pedido_id):
    if not puede_ver_localizacion_delivery(current_user):
        return _error_localizacion_restringida()
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        repartidor = obtener_repartidor_usuario(cliente_id, current_user.id_usuario)
        if repartidor:
            pedido_actual = next(
                (pedido for pedido in listar_ruta_repartidor(cliente_id, current_user.id_usuario)[1] if int(pedido.id_pedido) == int(pedido_id)),
                None,
            )
            if not pedido_actual:
                raise ValueError('El pedido no esta asignado a este repartidor.')
        elif not _puede_ver_ruta_operativa():
            raise ValueError('Este usuario no esta vinculado a un repartidor activo.')
        pedido = actualizar_destino_pedido_delivery(cliente_id, pedido_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': _serializar_pedidos_ruta([pedido])[0]})


def _marcar_ruta(pedido_id: int, estado: str):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        if obtener_repartidor_usuario(cliente_id, current_user.id_usuario):
            pedido = marcar_pedido_ruta(cliente_id, current_user.id_usuario, pedido_id, estado)
        elif _puede_ver_ruta_operativa():
            pedido = marcar_pedido_ruta_operativa(cliente_id, pedido_id, estado)
        else:
            raise ValueError('Este usuario no esta vinculado a un repartidor activo.')
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'pedido': _serializar_pedidos_ruta([pedido])[0]})


def _serializar_pedidos_ruta(pedidos):
    return ocultar_localizacion_pedidos(serializar_pedidos(pedidos), current_user)


def _error_localizacion_restringida():
    return jsonify({
        'error': 'delivery_location_restricted',
        'mensaje': 'La localizacion de delivery esta restringida al usuario root.',
    }), 403


def _error_gps_sin_permiso():
    return jsonify({
        'error': 'Sin permisos',
        'mensaje': 'No tienes permiso para registrar ubicacion GPS en delivery.',
        'permiso_requerido': PERMISO_DELIVERY_GPS,
    }), 403


def _puede_ver_ruta_operativa() -> bool:
    return tiene_permiso_gastronomia(PERMISO_POS, PERMISO_CAJA, PERMISO_COCINA)
