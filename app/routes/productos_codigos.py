"""
Rutas auxiliares para validar y sugerir codigos de productos.
"""
from flask import jsonify, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Producto
from app.utils.productos_errors import buscar_producto_por_codigo, sugerir_codigo_disponible


def register_codigo_routes(productos_bp):
    @productos_bp.route('/codigos/sugerencias')
    @login_required
    def sugerencias_codigos():
        if not _puede_consultar_codigos():
            return jsonify({'error': 'Sin permisos'}), 403

        q = (request.args.get('q') or '').strip()
        excluir_id = request.args.get('actual_id', type=int)
        if not q:
            return jsonify({'items': [], 'exacto': None, 'sugerencia': None})

        exacto = buscar_producto_por_codigo(q, excluir_id)
        like = f'%{q}%'
        query = Producto.query.filter(
            db.or_(
                Producto.codigo.ilike(like),
                Producto.codigo_barras.ilike(like),
                Producto.nombre.ilike(like),
            )
        )
        if excluir_id:
            query = query.filter(Producto.id_producto != excluir_id)

        productos = (
            query.order_by(Producto.activo.desc(), Producto.codigo.asc())
            .limit(8)
            .all()
        )

        return jsonify({
            'items': [_serializar_producto_codigo(p) for p in productos],
            'exacto': _serializar_producto_codigo(exacto) if exacto else None,
            'sugerencia': sugerir_codigo_disponible(q) if exacto else None,
        })


def _puede_consultar_codigos() -> bool:
    try:
        return (
            current_user.is_authenticated
            and (
                current_user.tiene_permiso('crear_producto')
                or current_user.tiene_permiso('editar_producto')
                or current_user.tiene_permiso('ver_inventario')
            )
        )
    except Exception:
        return False


def _serializar_producto_codigo(producto: Producto) -> dict:
    puede_editar = False
    try:
        puede_editar = current_user.tiene_permiso('editar_producto')
    except Exception:
        puede_editar = False

    data = {
        'id': int(producto.id_producto),
        'codigo': producto.codigo,
        'nombre': producto.nombre,
        'activo': bool(producto.activo),
        'estado': 'activo' if bool(producto.activo) else 'inactivo/eliminado',
    }
    if puede_editar:
        data['edit_url'] = url_for('productos.editar', id=producto.id_producto)
    return data
