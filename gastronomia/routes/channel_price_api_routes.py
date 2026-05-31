"""API para precios exclusivos de PedidosYa y Monchis."""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.channel_price_service import (
    guardar_precio_canal,
    listar_precios_canal,
)
from gastronomia.services.menu_service import listar_productos, obtener_producto
from gastronomia.services.permisos import PERMISO_MENU, requiere_permiso_gastronomia


gastronomia_channel_price_api_bp = Blueprint('gastronomia_channel_price_api', __name__)


def _cliente_o_error():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        return None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return cliente_id, None


@gastronomia_channel_price_api_bp.route('/precios-canales/<canal>', methods=['GET'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def precios_canal(canal):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    try:
        items = listar_precios_canal(cliente_id, canal, listar_productos(cliente_id))
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({
        'ok': True,
        'productos': [
            {
                'id_producto': item['producto'].id_producto,
                'nombre': item['producto'].nombre,
                'precio_normal': float(item['producto'].precio or 0),
                'precio_canal': item['precio_canal'].to_dict(),
            }
            for item in items
        ],
    })


@gastronomia_channel_price_api_bp.route('/precios-canales/<canal>/<int:producto_id>', methods=['PUT'])
@login_required
@requiere_permiso_gastronomia(PERMISO_MENU)
def actualizar_precio_canal(canal, producto_id):
    cliente_id, error = _cliente_o_error()
    if error:
        return error
    producto = obtener_producto(cliente_id, producto_id)
    if not producto:
        return jsonify({'error': 'not_found'}), 404
    data = request.get_json(silent=True) or {}
    try:
        item = guardar_precio_canal(cliente_id, producto, canal, data.get('precio'))
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, 'precio_canal': item.to_dict()})
