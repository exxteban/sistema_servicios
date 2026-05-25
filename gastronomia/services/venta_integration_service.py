"""Integracion de cobros gastronomicos con ventas y caja central."""
from __future__ import annotations

from decimal import Decimal

from app import db
from app.models.caja import MovimientoCaja, SesionCaja
from app.models.cliente import Cliente
from app.models.servicio import Servicio
from app.models.venta import DetalleVenta, MetodoPago, PagoVenta, Ticket, Venta
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem


METODO_BUSQUEDAS = {
    'efectivo': ('efectivo',),
    'tarjeta': ('tarjeta de debito', 'tarjeta'),
    'transferencia': ('transferencia',),
    'qr': ('qr', 'billetera'),
}


def crear_venta_central_desde_pedido(pedido: GastronomiaPedido, usuario_id: int, data: dict, *, descuento: Decimal):
    sesion = _sesion_abierta_usuario(usuario_id)
    if not sesion:
        raise ValueError('Debe abrir una caja antes de cobrar pedidos gastronomicos.')

    metodo = _resolver_metodo_pago(data)
    subtotal = Decimal(str(pedido.total or 0)).quantize(Decimal('0.01'))
    total = (subtotal - descuento).quantize(Decimal('0.01'))
    if total < 0:
        raise ValueError('El total del pedido no puede ser negativo.')

    venta = Venta(
        id_cliente=_consumidor_final_id(),
        id_sesion_caja=sesion.id_sesion,
        id_usuario_vendedor=pedido.usuario_id,
        subtotal=subtotal,
        descuento_monto=descuento,
        descuento_manual_monto=descuento,
        descuento_fidelizacion_monto=Decimal('0.00'),
        total_iva_10=Decimal('0.00'),
        total_iva_5=Decimal('0.00'),
        total_exenta=Decimal('0.00'),
        total=total,
        tipo_venta='contado',
        observaciones=_observaciones_venta(pedido, data),
    )
    db.session.add(venta)
    db.session.flush()

    total_iva_10, total_iva_5, total_exenta = _registrar_detalles(venta, pedido)
    venta.total_iva_10 = total_iva_10
    venta.total_iva_5 = total_iva_5
    venta.total_exenta = total_exenta

    pago_venta = PagoVenta(
        id_venta=venta.id_venta,
        id_metodo_pago=metodo.id_metodo_pago,
        monto=total,
        referencia=(data.get('referencia') or '').strip()[:100] or None,
    )
    db.session.add(pago_venta)

    movimiento = None
    if _es_metodo_efectivo(metodo):
        movimiento = MovimientoCaja(
            id_sesion_caja=sesion.id_sesion,
            id_usuario=int(usuario_id),
            tipo='ingreso',
            monto=total,
            motivo=f'Cobro Efectivo Pedido Gastronomia #{pedido.id_pedido}',
            referencia_tipo='venta',
            referencia_id=venta.id_venta,
            fecha_movimiento=venta.fecha_venta,
        )
        db.session.add(movimiento)

    db.session.flush()
    db.session.add(Ticket(
        id_venta=venta.id_venta,
        numero_ticket=f'TK-{venta.id_venta:06d}',
        id_usuario_emision=int(usuario_id),
    ))

    return {
        'venta': venta,
        'sesion': sesion,
        'metodo': metodo,
        'movimiento': movimiento,
        'metodo_slug': _slug_metodo(metodo),
    }


def _sesion_abierta_usuario(usuario_id: int):
    return SesionCaja.query.filter_by(id_usuario=int(usuario_id), estado='abierta').first()


def _resolver_metodo_pago(data: dict) -> MetodoPago:
    metodo_id = data.get('id_metodo_pago')
    if metodo_id not in (None, ''):
        metodo = db.session.get(MetodoPago, int(metodo_id))
        if metodo and bool(getattr(metodo, 'activo', True)):
            return metodo
        raise ValueError('Metodo de pago no encontrado o inactivo.')

    metodo_slug = (data.get('metodo_pago') or 'efectivo').strip().lower()
    if metodo_slug == 'mixto':
        return _metodo_pago_mixto()
    for patron in METODO_BUSQUEDAS.get(metodo_slug, (metodo_slug,)):
        metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike(f'%{patron}%'), MetodoPago.activo == True).first()
        if metodo:
            return metodo
    raise ValueError('Metodo de pago invalido o no configurado.')


def _metodo_pago_mixto() -> MetodoPago:
    metodo = MetodoPago.query.filter(MetodoPago.nombre.ilike('%mixto%')).first()
    if metodo:
        metodo.activo = True
        return metodo
    metodo = MetodoPago(
        nombre='Pago Mixto',
        requiere_referencia=False,
        orden_display=90,
        activo=True,
    )
    db.session.add(metodo)
    db.session.flush()
    return metodo


def _registrar_detalles(venta: Venta, pedido: GastronomiaPedido):
    total_iva_10 = Decimal('0.00')
    total_iva_5 = Decimal('0.00')
    total_exenta = Decimal('0.00')
    for item in pedido.items.order_by(GastronomiaPedidoItem.id_item.asc()).all():
        servicio = _servicio_para_item(item)
        cantidad = max(int(item.cantidad or 1), 1)
        subtotal = Decimal(str(item.subtotal or 0)).quantize(Decimal('0.01'))
        precio_unitario = (subtotal / Decimal(cantidad)).quantize(Decimal('0.01'))
        monto_iva = _iva_incluido(subtotal, int(servicio.porcentaje_iva or 0))
        if int(servicio.porcentaje_iva or 0) == 10:
            total_iva_10 += monto_iva
        elif int(servicio.porcentaje_iva or 0) == 5:
            total_iva_5 += monto_iva
        else:
            total_exenta += subtotal
        db.session.add(DetalleVenta(
            id_venta=venta.id_venta,
            id_servicio=servicio.id_servicio,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            precio_original=precio_unitario,
            porcentaje_iva=int(servicio.porcentaje_iva or 0),
            monto_iva=monto_iva,
            subtotal=subtotal,
            es_kit=False,
        ))
    return total_iva_10, total_iva_5, total_exenta


def _servicio_para_item(item) -> Servicio:
    codigo = f'GASTRO-{int(item.cliente_id)}-{int(item.producto_id)}'
    servicio = Servicio.query.filter_by(codigo=codigo).first()
    precio = Decimal(str(item.precio_unitario or 0)).quantize(Decimal('0.01'))
    if not servicio:
        servicio = Servicio(
            codigo=codigo,
            nombre=item.nombre_producto,
            categoria='Gastronomia',
            descripcion='Servicio generado automaticamente desde menu gastronomico.',
            costo=Decimal('0.00'),
            precio=precio,
            duracion_minutos=0,
            porcentaje_iva=10,
            activo=True,
        )
        db.session.add(servicio)
        db.session.flush()
        return servicio
    servicio.nombre = item.nombre_producto
    servicio.precio = precio
    servicio.activo = True
    return servicio


def _iva_incluido(subtotal: Decimal, porcentaje: int) -> Decimal:
    if porcentaje == 10:
        return (subtotal / Decimal('11')).quantize(Decimal('0.01'))
    if porcentaje == 5:
        return (subtotal / Decimal('21')).quantize(Decimal('0.01'))
    return Decimal('0.00')


def _consumidor_final_id() -> int:
    consumidor = Cliente.query.get(1)
    if consumidor:
        return int(consumidor.id_cliente)
    consumidor = Cliente(nombre='CONSUMIDOR FINAL', ruc_ci='00000000-0', tipo='minorista', activo=True)
    db.session.add(consumidor)
    db.session.flush()
    return int(consumidor.id_cliente)


def _es_metodo_efectivo(metodo: MetodoPago) -> bool:
    return 'efectivo' in (metodo.nombre or '').strip().lower()


def _slug_metodo(metodo: MetodoPago) -> str:
    nombre = (metodo.nombre or '').strip().lower()
    if 'efectivo' in nombre:
        return 'efectivo'
    if 'transferencia' in nombre:
        return 'transferencia'
    if 'qr' in nombre or 'billetera' in nombre:
        return 'qr'
    if 'tarjeta' in nombre:
        return 'tarjeta'
    if 'mixto' in nombre:
        return 'mixto'
    return nombre[:40] or 'efectivo'


def _observaciones_venta(pedido: GastronomiaPedido, data: dict) -> str:
    partes = [f'Pedido gastronomia #{pedido.id_pedido}']
    if pedido.mesa:
        partes.append(f'Mesa {pedido.mesa}')
    if pedido.notas:
        partes.append(f'Notas: {pedido.notas}')
    observacion = (data.get('observacion') or '').strip()
    if observacion:
        partes.append(observacion)
    return ' | '.join(partes)
