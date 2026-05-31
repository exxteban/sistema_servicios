"""
API de promociones de tienda.
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app import db
from app.models.producto import Producto
from app.models.tienda_promocion import TiendaPromocion
from app.services.tienda_promociones import (
    get_active_promotions_for_store,
    list_admin_promotions,
    save_promotion,
    serialize_admin_promotion,
    serialize_public_promotion,
)
from app.utils.permisos import requiere_permiso
from app.routes.tienda_api import _config_por_slug, _resolver_id_cliente_actual
from gastronomia.models import GastronomiaProducto


tienda_promociones_api_bp = Blueprint('tienda_promociones_api', __name__)


def _resolve_client_id(data: dict | None = None) -> int | None:
    client_id = _resolver_id_cliente_actual(data or {})
    try:
        return int(client_id) if client_id else None
    except (TypeError, ValueError):
        return None


def _promotion_for_client_or_404(promotion_id: int, client_id: int):
    return TiendaPromocion.query.filter_by(
        id_promocion=promotion_id,
        id_cliente=client_id,
    ).first_or_404()


@tienda_promociones_api_bp.route('/<slug>/promociones', methods=['GET'])
def get_public_promotions(slug: str):
    config = _config_por_slug(slug)
    if not config:
        return jsonify({'error': 'tienda_no_encontrada'}), 404

    promotions = get_active_promotions_for_store(config)
    return jsonify([
        serialize_public_promotion(promotion, include_products=True)
        for promotion in promotions
    ])


@tienda_promociones_api_bp.route('/admin/promociones', methods=['GET'])
@login_required
@requiere_permiso('editar_configuracion')
def admin_list_promotions():
    client_id = _resolve_client_id(request.args)
    if not client_id:
        return jsonify({'error': 'cliente_no_encontrado'}), 404

    promotions = list_admin_promotions(client_id)
    return jsonify({
        'ok': True,
        'promociones': [serialize_admin_promotion(promotion) for promotion in promotions],
    })


@tienda_promociones_api_bp.route('/admin/promociones', methods=['POST'])
@login_required
@requiere_permiso('editar_configuracion')
def admin_create_promotion():
    data = request.get_json(silent=True) or {}
    client_id = _resolve_client_id(data)
    if not client_id:
        return jsonify({'error': 'cliente_no_encontrado'}), 404

    promotion, error = save_promotion(
        promotion=None,
        client_id=client_id,
        data=data,
    )
    if error:
        return jsonify({'error': error}), 400

    db.session.commit()
    return jsonify({'ok': True, 'promocion': serialize_admin_promotion(promotion)}), 201


@tienda_promociones_api_bp.route('/admin/promociones/<int:promotion_id>', methods=['PUT'])
@login_required
@requiere_permiso('editar_configuracion')
def admin_update_promotion(promotion_id: int):
    data = request.get_json(silent=True) or {}
    client_id = _resolve_client_id(data)
    if not client_id:
        return jsonify({'error': 'cliente_no_encontrado'}), 404

    promotion = _promotion_for_client_or_404(promotion_id, client_id)
    updated, error = save_promotion(
        promotion=promotion,
        client_id=client_id,
        data=data,
    )
    if error:
        return jsonify({'error': error}), 400

    db.session.commit()
    return jsonify({'ok': True, 'promocion': serialize_admin_promotion(updated)})


@tienda_promociones_api_bp.route('/admin/promociones/<int:promotion_id>', methods=['DELETE'])
@login_required
@requiere_permiso('editar_configuracion')
def admin_delete_promotion(promotion_id: int):
    client_id = _resolve_client_id(request.args)
    if not client_id:
        return jsonify({'error': 'cliente_no_encontrado'}), 404

    promotion = _promotion_for_client_or_404(promotion_id, client_id)
    db.session.delete(promotion)
    db.session.commit()
    return jsonify({'ok': True})


@tienda_promociones_api_bp.route('/admin/promociones/productos', methods=['GET'])
@login_required
@requiere_permiso('editar_configuracion')
def admin_search_promotion_products():
    data = request.args.to_dict()
    client_id = _resolve_client_id(data)
    if not client_id:
        return jsonify({'error': 'cliente_no_encontrado'}), 404

    q = (request.args.get('q') or '').strip()
    limit = min(30, max(5, request.args.get('limit', 12, type=int)))

    query = Producto.query.filter(
        Producto.activo.is_(True),
        db.or_(Producto.id_cliente == client_id, Producto.id_cliente.is_(None)),
    )
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Producto.nombre.ilike(like),
                Producto.codigo.ilike(like),
                Producto.marca.ilike(like),
                Producto.modelo.ilike(like),
            )
        )

    products = query.order_by(Producto.nombre.asc()).limit(limit).all()
    gastro_query = GastronomiaProducto.query.filter(
        GastronomiaProducto.cliente_id == int(client_id),
        GastronomiaProducto.activo.is_(True),
    )
    if q:
        like = f'%{q}%'
        gastro_query = gastro_query.filter(
            db.or_(
                GastronomiaProducto.nombre.ilike(like),
                GastronomiaProducto.descripcion.ilike(like),
            )
        )
    gastro_products = gastro_query.order_by(GastronomiaProducto.nombre.asc()).limit(limit).all()
    return jsonify({
        'ok': True,
        'productos': ([
            {
                'id_producto': product.id_producto,
                'codigo': product.codigo,
                'nombre': product.nombre,
                'precio_venta': float(product.precio_venta or 0),
                'tipo_catalogo': 'producto',
            }
            for product in products
        ] + [
            {
                'id_producto': product.id_producto,
                'codigo': 'GASTRO',
                'nombre': product.nombre,
                'precio_venta': float(product.precio or 0),
                'tipo_catalogo': 'gastronomia',
            }
            for product in gastro_products
        ])[:limit],
    })
