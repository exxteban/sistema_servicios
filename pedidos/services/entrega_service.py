from datetime import UTC, datetime
from decimal import Decimal

from app import db
from app.models import DetalleVenta, MovimientoStock, SesionCaja, Ticket, Venta
from pedidos.models import PedidoCliente
from pedidos.schema import ESTADO_PEDIDO_CANCELADO, ESTADO_PEDIDO_ENTREGADO
from pedidos.services.pedido_service import (
    _clean_text,
    _to_decimal,
    obtener_producto_activo_bloqueado,
    registrar_historial,
)


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def _obtener_sesion_abierta_usuario(id_usuario: int) -> SesionCaja | None:
    return SesionCaja.query.filter_by(id_usuario=id_usuario, estado='abierta').first()


def _validar_entrega_pedido(pedido: PedidoCliente):
    if not pedido:
        raise ValueError('Pedido invalido.')
    if int(getattr(pedido, 'id_venta_generada', 0) or 0) > 0:
        raise ValueError('El pedido ya fue entregado y convertido a venta.')
    estado_actual = (pedido.estado or '').strip()
    if estado_actual == ESTADO_PEDIDO_CANCELADO:
        raise ValueError('No se puede entregar un pedido cancelado.')
    if estado_actual == ESTADO_PEDIDO_ENTREGADO:
        raise ValueError('El pedido ya fue entregado.')
    if not pedido.detalles.count():
        raise ValueError('El pedido no tiene items para entregar.')
    saldo = _to_decimal(pedido.saldo_pendiente)
    if saldo > Decimal('0.00'):
        raise ValueError('No se puede entregar un pedido con saldo pendiente.')


def confirmar_entrega_y_generar_venta(pedido: PedidoCliente, *, id_usuario: int):
    _validar_entrega_pedido(pedido)

    sesion = _obtener_sesion_abierta_usuario(id_usuario)
    if sesion is None:
        raise ValueError('Debe tener una caja abierta para confirmar la entrega del pedido.')

    detalles_pedido = pedido.detalles.all()
    subtotal = _to_decimal(pedido.subtotal)
    total = _to_decimal(pedido.total)
    descuento = _to_decimal(pedido.descuento_monto)
    total_iva_10 = Decimal('0.00')
    total_iva_5 = Decimal('0.00')
    total_exenta = Decimal('0.00')

    detalles_venta = []
    for item in detalles_pedido:
        producto = obtener_producto_activo_bloqueado(int(item.id_producto))
        if producto is None or not bool(getattr(producto, 'activo', True)):
            raise ValueError(f'El producto #{int(item.id_producto or 0)} ya no esta disponible para entregar.')

        cantidad = int(item.cantidad or 0)
        if cantidad <= 0:
            raise ValueError(f'Cantidad invalida en el item {item.producto_nombre_snapshot}.')

        if not bool(getattr(producto, 'es_servicio', False)):
            stock_actual = int(getattr(producto, 'stock_actual', 0) or 0)
            if stock_actual < cantidad:
                raise ValueError(
                    f'Stock insuficiente para {producto.nombre}. Disponible: {stock_actual}, requerido: {cantidad}.'
                )

        item_subtotal = _to_decimal(item.subtotal or (_to_decimal(item.precio_unitario) * cantidad))
        porcentaje_iva = int(item.porcentaje_iva or getattr(producto, 'porcentaje_iva', 0) or 0)
        if porcentaje_iva == 10:
            monto_iva = (item_subtotal / Decimal('11')).quantize(Decimal('0.01'))
            total_iva_10 += monto_iva
        elif porcentaje_iva == 5:
            monto_iva = (item_subtotal / Decimal('21')).quantize(Decimal('0.01'))
            total_iva_5 += monto_iva
        else:
            monto_iva = Decimal('0.00')
            total_exenta += item_subtotal

        detalles_venta.append(
            {
                'pedido_item': item,
                'producto': producto,
                'cantidad': cantidad,
                'detalle': DetalleVenta(
                    id_producto=int(producto.id_producto),
                    cantidad=cantidad,
                    precio_unitario=_to_decimal(item.precio_unitario).quantize(Decimal('0.01')),
                    precio_original=_to_decimal(item.precio_unitario).quantize(Decimal('0.01')),
                    porcentaje_iva=porcentaje_iva,
                    monto_iva=monto_iva,
                    subtotal=item_subtotal.quantize(Decimal('0.01')),
                    es_kit=bool(getattr(producto, 'es_kit', False)),
                ),
            }
        )

    venta = Venta(
        id_cliente=int(pedido.id_cliente),
        id_sesion_caja=int(sesion.id_sesion),
        id_usuario_vendedor=int(id_usuario),
        fecha_venta=_utcnow(),
        subtotal=subtotal.quantize(Decimal('0.01')),
        descuento_monto=descuento.quantize(Decimal('0.01')),
        total_iva_10=total_iva_10.quantize(Decimal('0.01')),
        total_iva_5=total_iva_5.quantize(Decimal('0.01')),
        total_exenta=total_exenta.quantize(Decimal('0.01')),
        total=total.quantize(Decimal('0.01')),
        estado='completada',
        tipo_venta='contado',
        saldo_pendiente=Decimal('0.00'),
        observaciones=_clean_text(
            f'Generada desde {pedido.numero_pedido_display}. {(pedido.observaciones or "").strip()}',
            500,
        )
        or None,
    )
    db.session.add(venta)
    db.session.flush()

    for detalle_ctx in detalles_venta:
        detalle = detalle_ctx['detalle']
        producto = detalle_ctx['producto']
        cantidad = detalle_ctx['cantidad']
        detalle.id_venta = int(venta.id_venta)
        db.session.add(detalle)

        if bool(getattr(producto, 'es_servicio', False)):
            continue

        stock_anterior = int(producto.stock_actual or 0)
        producto.stock_actual = stock_anterior - cantidad
        db.session.add(
            MovimientoStock(
                id_producto=int(producto.id_producto),
                id_usuario=int(id_usuario),
                tipo_movimiento='salida',
                cantidad=cantidad,
                stock_anterior=stock_anterior,
                stock_nuevo=int(producto.stock_actual or 0),
                referencia_tipo='venta',
                referencia_id=int(venta.id_venta),
                motivo=f'Entrega de pedido {pedido.numero_pedido_display} convertida en venta #{int(venta.id_venta)}',
                fecha_movimiento=venta.fecha_venta,
            )
        )

    db.session.add(
        Ticket(
            id_venta=int(venta.id_venta),
            numero_ticket=f'TK-{int(venta.id_venta):06d}',
            id_usuario_emision=int(id_usuario),
        )
    )

    pedido.id_venta_generada = int(venta.id_venta)
    pedido.estado = ESTADO_PEDIDO_ENTREGADO
    pedido.id_usuario_modificacion = int(id_usuario)
    registrar_historial(
        pedido,
        f'Se confirmo la entrega y se genero la venta #{int(venta.id_venta)}.',
        'entrega_confirmada',
        id_usuario=id_usuario,
    )

    return {
        'pedido': pedido,
        'venta': venta,
        'sesion': sesion,
    }
