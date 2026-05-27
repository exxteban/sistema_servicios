"""Pantalla de caja gastronomica."""
from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.models import Configuracion, SesionCaja
from gastronomia.models import GastronomiaPedidoItem, GastronomiaPedidoItemModificador
from gastronomia.routes.dashboard_routes import gastronomia_bp
from gastronomia.services.access import cliente_id_actual_gastronomia, mensaje_contexto_gastronomia
from gastronomia.services.pedido_service import obtener_pedido
from gastronomia.services.permisos import PERMISO_CAJA, requiere_permiso_gastronomia


@gastronomia_bp.route('/caja')
@login_required
@requiere_permiso_gastronomia(PERMISO_CAJA)
def caja():
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    sesion_caja_abierta = SesionCaja.query.filter_by(id_usuario=current_user.id_usuario, estado='abierta').first()
    return render_template('gastronomia/caja.html', sesion_caja_abierta=sesion_caja_abierta)


@gastronomia_bp.route('/pedidos/<int:pedido_id>/ticket')
@login_required
@requiere_permiso_gastronomia(PERMISO_CAJA)
def ticket_pedido(pedido_id):
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        flash(mensaje_contexto_gastronomia(), 'warning')
        return redirect(url_for('main.dashboard'))
    pedido = obtener_pedido(cliente_id, pedido_id)
    if pedido is None:
        abort(404)
    return render_template('gastronomia/ticket.html', **_ticket_context(pedido))


def _ticket_context(pedido):
    paper_width_mm = Configuracion.obtener_int('ticket_paper_width_mm', 58)
    if paper_width_mm not in (48, 58, 80):
        paper_width_mm = 58
    pago = pedido.pago
    descuento = float(getattr(pago, 'descuento_monto', 0) or 0) if pago else 0
    total_cobrado = float(getattr(pago, 'total_cobrado', pedido.total) or 0) if pago else float(pedido.total or 0)
    return {
        'pedido': pedido,
        'items': [_ticket_item(item) for item in pedido.items.order_by(GastronomiaPedidoItem.id_item.asc()).all()],
        'empresa': _empresa_ticket(pedido),
        'pago': pago,
        'subtotal': float(pedido.total or 0),
        'descuento': descuento,
        'total_cobrado': total_cobrado,
        'metodo_pago_label': _metodo_pago_label(getattr(pago, 'metodo_pago', 'pendiente')),
        'footer_text': Configuracion.obtener('ticket_footer_text', 'Gracias por su compra') or 'Gracias por su compra',
        'paper_width_mm': paper_width_mm,
    }


def _ticket_item(item):
    modificadores = []
    for modificador in item.modificadores.order_by(GastronomiaPedidoItemModificador.id_modificador.asc()).all():
        nombre = modificador.nombre_opcion
        if modificador.tipo_grupo == 'ingrediente_removible':
            nombre = f'Sin {nombre}'
        modificadores.append(nombre)
    return {
        'nombre': item.nombre_producto,
        'cantidad': int(item.cantidad or 0),
        'precio_unitario': float(item.precio_unitario or 0),
        'subtotal': float(item.subtotal or 0),
        'modificadores': modificadores,
        'notas': item.notas,
    }


def _empresa_ticket(pedido):
    cliente = getattr(pedido, 'cliente', None)
    return {
        'nombre': Configuracion.obtener('nombre_empresa', '') or getattr(cliente, 'nombre', '') or 'Gastronomia',
        'ruc': Configuracion.obtener('ruc_empresa', '') or getattr(cliente, 'ruc_ci', '') or '',
        'direccion': Configuracion.obtener('direccion_empresa', '') or getattr(cliente, 'direccion', '') or '',
        'telefono': Configuracion.obtener('telefono_empresa', '') or getattr(cliente, 'telefono', '') or '',
    }


def _metodo_pago_label(metodo):
    labels = {
        'efectivo': 'Efectivo',
        'tarjeta': 'Tarjeta',
        'transferencia': 'Transferencia',
        'qr': 'QR / Billetera',
        'mixto': 'Pago mixto',
        'pendiente': 'Pendiente',
    }
    return labels.get((metodo or '').strip().lower(), metodo or 'Pendiente')
