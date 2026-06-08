"""API publica de pedidos gastronomicos desde tienda online."""
from flask import Blueprint, jsonify, request

from app import csrf
from app.models.tienda import TiendaConfig
from app.services.tienda_context import resolver_cliente_gastronomia_tienda
from app.services.tienda_presupuesto import tienda_es_gastronomia
from gastronomia.services.cliente_final_service import (
    crear_pedido_publico_gastronomia,
    perfil_cliente_publico,
    whatsapp_pedido_url,
)


tienda_gastronomia_api_bp = Blueprint('tienda_gastronomia_api', __name__)


def _config_gastronomia(slug: str):
    config = TiendaConfig.query.filter_by(slug=(slug or '').strip().lower(), activa=True).first()
    if not config:
        return None, None, (jsonify({'error': 'tienda_no_encontrada'}), 404)
    if not tienda_es_gastronomia(config):
        return None, None, (jsonify({'error': 'tienda_no_gastronomia'}), 400)
    cliente_id = resolver_cliente_gastronomia_tienda(config)
    if not cliente_id:
        return None, None, (jsonify({'error': 'gastronomia_no_activa'}), 403)
    return config, cliente_id, None


@tienda_gastronomia_api_bp.route('/<slug>/gastronomia/perfil', methods=['GET'])
def perfil_gastronomia(slug: str):
    _config, cliente_id, error = _config_gastronomia(slug)
    if error:
        return error
    try:
        data = perfil_cliente_publico(
            cliente_id,
            request.args.get('telefono') or '',
            request.args.get('token') or '',
        )
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    return jsonify({'ok': True, **data})


@tienda_gastronomia_api_bp.route('/<slug>/gastronomia/pedido', methods=['POST'])
@csrf.exempt
def crear_pedido_gastronomia(slug: str):
    config, cliente_id, error = _config_gastronomia(slug)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    tipo_pedido = (data.get('tipo_pedido') or 'delivery').strip().lower()
    if not config.tienda_delivery_activo and not config.tienda_retiro_activo:
        return jsonify({'error': 'sin_modalidades', 'mensaje': 'La tienda no tiene modalidades de pedido activas.'}), 400
    if tipo_pedido == 'delivery' and not config.tienda_delivery_activo:
        return jsonify({'error': 'delivery_no_disponible', 'mensaje': 'Esta tienda no tiene delivery activo.'}), 400
    if tipo_pedido == 'retiro' and not config.tienda_retiro_activo:
        return jsonify({'error': 'retiro_no_disponible', 'mensaje': 'Esta tienda no tiene retiro activo.'}), 400
    try:
        result = crear_pedido_publico_gastronomia(cliente_id, data)
    except ValueError as exc:
        return jsonify({'error': 'validation_error', 'mensaje': str(exc)}), 400
    result['whatsapp_url'] = whatsapp_pedido_url(
        config.telefono_whatsapp,
        result['pedido'],
        config.nombre_tienda,
    )
    return jsonify({'ok': True, **result}), 201
