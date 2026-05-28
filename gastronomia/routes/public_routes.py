"""Seguimiento publico de pedidos gastronomicos."""
from flask import abort, render_template

from gastronomia.models import GastronomiaPedido, GastronomiaPedidoEvento
from gastronomia.routes.dashboard_routes import gastronomia_bp


@gastronomia_bp.route('/pedido/<codigo_publico>')
def seguimiento_pedido_publico(codigo_publico):
    codigo = (codigo_publico or '').strip().upper()[:32]
    if not codigo:
        abort(404)
    pedido = GastronomiaPedido.query.filter_by(codigo_publico=codigo).first()
    if pedido is None:
        abort(404)
    eventos = (
        GastronomiaPedidoEvento.query
        .filter_by(pedido_id=pedido.id_pedido)
        .order_by(GastronomiaPedidoEvento.fecha_evento.asc())
        .all()
    )
    return render_template('gastronomia/seguimiento_pedido.html', pedido=pedido, eventos=eventos)
