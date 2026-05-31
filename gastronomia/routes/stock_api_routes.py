"""API de configuracion del inventario gastronomico."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia
from gastronomia.services.stock_service import (
    ajustar_stock,
    configurar_insumo,
    eliminar_presentacion,
    guardar_presentacion,
    guardar_receta,
    listar_insumos,
    listar_resumen_recetas,
    obtener_receta,
    registrar_entrada,
    serializar_insumo,
)


gastronomia_stock_api_bp = Blueprint('gastronomia_stock_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return cliente_id, None


def _payload():
    return request.get_json(silent=True) or {}


@gastronomia_stock_api_bp.route('/stock/insumos', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def insumos():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    return jsonify({
        'ok': True,
        'insumos': [serializar_insumo(item) for item in listar_insumos(cliente_id)],
    })


@gastronomia_stock_api_bp.route('/stock/insumos/<int:insumo_id>', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def actualizar_insumo(insumo_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        insumo = configurar_insumo(cliente_id, insumo_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'insumo': serializar_insumo(insumo)})


@gastronomia_stock_api_bp.route('/stock/insumos/<int:insumo_id>/presentaciones', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def crear_presentacion(insumo_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        presentacion = guardar_presentacion(cliente_id, insumo_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'presentacion': presentacion.to_dict()}), 201


@gastronomia_stock_api_bp.route('/stock/presentaciones/<int:presentacion_id>', methods=['DELETE'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def borrar_presentacion(presentacion_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    if not eliminar_presentacion(cliente_id, presentacion_id):
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'ok': True})


@gastronomia_stock_api_bp.route('/stock/insumos/<int:insumo_id>/entradas', methods=['POST'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def crear_entrada(insumo_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        insumo = registrar_entrada(cliente_id, current_user.id_usuario, insumo_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'insumo': serializar_insumo(insumo)})


@gastronomia_stock_api_bp.route('/stock/insumos/<int:insumo_id>/ajuste', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def ajustar_insumo(insumo_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        insumo = ajustar_stock(cliente_id, current_user.id_usuario, insumo_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'insumo': serializar_insumo(insumo)})


@gastronomia_stock_api_bp.route('/stock/productos/<int:producto_id>/receta', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def receta(producto_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        data = obtener_receta(cliente_id, producto_id)
    except ValueError as exc:
        return jsonify({'error': 'not_found', 'mensaje': str(exc)}), 404
    return jsonify({'ok': True, 'receta': data})


@gastronomia_stock_api_bp.route('/stock/recetas/resumen', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def resumen_recetas():
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    return jsonify({'ok': True, 'productos': listar_resumen_recetas(cliente_id)})


@gastronomia_stock_api_bp.route('/stock/productos/<int:producto_id>/receta', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def actualizar_receta(producto_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        data = guardar_receta(cliente_id, producto_id, _payload())
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'receta': data})
