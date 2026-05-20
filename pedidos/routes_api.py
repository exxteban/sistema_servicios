from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from pedidos.models import PedidoCliente
from pedidos.services.pedido_service import buscar_productos_para_pedido


pedidos_api_bp = Blueprint(
    'pedidos_api',
    __name__,
)


def _puede_ver_pedidos() -> bool:
    return current_user.es_admin() or current_user.tiene_permiso('ver_clientes')


def _puede_buscar_productos_pedido() -> bool:
    return (
        _puede_ver_pedidos()
        or current_user.tiene_permiso('editar_cliente')
        or current_user.tiene_permiso('crear_cliente')
    )


@pedidos_api_bp.route('/api/productos')
@login_required
def buscar_productos():
    if not _puede_buscar_productos_pedido():
        return jsonify({'success': False, 'error': 'Sin permisos'}), 403

    resultados = buscar_productos_para_pedido(request.args.get('q', ''), limit=request.args.get('limit', 20, type=int))
    return jsonify({
        'success': True,
        'items': [
            {
                'id_producto': producto.id_producto,
                'codigo': producto.codigo,
                'nombre': producto.nombre,
                'precio_venta': float(producto.precio_venta or 0),
                'stock_actual': int(producto.stock_actual or 0),
                'stock_reservado_pedidos': int(getattr(producto, 'stock_reservado_pedidos', 0) or 0),
                'stock_disponible_pedidos': (
                    int(getattr(producto, 'stock_disponible_pedidos', 0) or 0)
                    if getattr(producto, 'stock_disponible_pedidos', None) is not None else None
                ),
            }
            for producto in resultados
        ],
    })


@pedidos_api_bp.route('/api/<int:id_pedido>')
@login_required
def detalle_pedido_json(id_pedido: int):
    if not _puede_ver_pedidos():
        return jsonify({'success': False, 'error': 'Sin permisos'}), 403

    pedido = PedidoCliente.query.get_or_404(id_pedido)
    return jsonify({
        'success': True,
        'pedido': {
            'id_pedido': pedido.id_pedido,
            'numero': pedido.numero_pedido_display,
            'estado': pedido.estado,
            'estado_label': pedido.estado_label,
            'cliente': pedido.cliente.nombre if pedido.cliente else '',
            'subtotal': float(pedido.subtotal or 0),
            'total': float(pedido.total or 0),
            'total_pagado': float(pedido.total_pagado or 0),
            'saldo_pendiente': float(pedido.saldo_pendiente or 0),
            'items': [
                {
                    'id_detalle_pedido': item.id_detalle_pedido,
                    'id_producto': item.id_producto,
                    'producto': item.producto_nombre_snapshot,
                    'cantidad': int(item.cantidad or 0),
                    'precio_unitario': float(item.precio_unitario or 0),
                    'subtotal': float(item.subtotal or 0),
                }
                for item in pedido.detalles.all()
            ],
            'pagos': [
                {
                    'id_pago_pedido': pago.id_pago_pedido,
                    'tipo_pago': pago.tipo_pago,
                    'metodo': pago.metodo.nombre if pago.metodo else '',
                    'monto': float(pago.monto or 0),
                    'referencia': pago.referencia or '',
                    'fecha_pago': pago.fecha_pago.isoformat() if pago.fecha_pago else None,
                }
                for pago in pedido.pagos.filter_by(estado='activo').all()
            ],
        },
    })
