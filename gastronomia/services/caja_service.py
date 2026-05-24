"""Cobro de pedidos gastronomicos."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app import db
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoPago
from gastronomia.services.pedido_service import listar_pedidos, obtener_pedido, registrar_evento_pedido


METODOS_PAGO = {'efectivo', 'tarjeta', 'transferencia', 'qr', 'mixto'}
ESTADOS_COBRABLES = {'abierto', 'enviado_cocina', 'preparando', 'listo', 'entregado'}


def listar_pedidos_caja(cliente_id: int) -> list[GastronomiaPedido]:
    return listar_pedidos(
        cliente_id,
        estados=['abierto', 'enviado_cocina', 'preparando', 'listo', 'entregado'],
    )


def cobrar_pedido(cliente_id: int, usuario_id: int, pedido_id: int, data: dict) -> GastronomiaPedido:
    pedido = obtener_pedido(cliente_id, pedido_id)
    if not pedido:
        raise ValueError('Pedido no encontrado.')
    if pedido.estado == 'cobrado' or pedido.pago:
        raise ValueError('El pedido ya fue cobrado.')
    if pedido.estado == 'cancelado':
        raise ValueError('No se puede cobrar un pedido cancelado.')
    if pedido.estado not in ESTADOS_COBRABLES:
        raise ValueError('El pedido no esta disponible para cobro.')

    metodo_pago = (data.get('metodo_pago') or 'efectivo').strip().lower()
    if metodo_pago not in METODOS_PAGO:
        raise ValueError('Metodo de pago invalido.')

    subtotal = Decimal(str(pedido.total or 0)).quantize(Decimal('0.01'))
    descuento = _parse_decimal(data.get('descuento_monto'), Decimal('0.00'))
    if descuento < 0:
        raise ValueError('El descuento no puede ser negativo.')
    if descuento > subtotal:
        raise ValueError('El descuento no puede superar el total del pedido.')

    pago = GastronomiaPedidoPago(
        cliente_id=int(cliente_id),
        pedido_id=int(pedido.id_pedido),
        usuario_id=int(usuario_id),
        metodo_pago=metodo_pago,
        subtotal=subtotal,
        descuento_monto=descuento,
        total_cobrado=subtotal - descuento,
        observacion=(data.get('observacion') or '').strip()[:255] or None,
    )
    pedido.estado = 'cobrado'
    db.session.add(pago)
    db.session.commit()
    registrar_evento_pedido(pedido, 'pedido_cobrado')
    return pedido


def _parse_decimal(value, default: Decimal) -> Decimal:
    if value in (None, ''):
        return default
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Monto invalido.')
