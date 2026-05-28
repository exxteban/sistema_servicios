"""Pantalla POS touch para toma de pedidos."""
from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.menu_service import listar_categorias
from gastronomia.services.pedido_service import obtener_pedido
from gastronomia.services.permisos import (
    PERMISO_CAJA,
    PERMISO_POS,
    requiere_permiso_gastronomia,
    tiene_permiso_gastronomia,
)


@gastronomia_bp.route('/pos')
@login_required
@requiere_permiso_gastronomia(PERMISO_POS)
def pos():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    pedido_inicial = None
    pedido_id = request.args.get('pedido', type=int)
    if pedido_id:
        pedido = obtener_pedido(cliente_id, pedido_id)
        if pedido and pedido.estado == 'abierto' and not pedido.pago:
            pedido_inicial = pedido
        else:
            flash('Solo se pueden editar pedidos abiertos pendientes de cobro.', 'warning')
    return render_template(
        'gastronomia/pos.html',
        categorias=listar_categorias(cliente_id, incluir_ocultas=False),
        mesa_inicial=(request.args.get('mesa') or '').strip()[:40],
        tipo_inicial=(request.args.get('tipo') or '').strip().lower(),
        pedido_inicial_id=int(pedido_inicial.id_pedido) if pedido_inicial else None,
        puede_cobrar=tiene_permiso_gastronomia(PERMISO_CAJA),
    )
