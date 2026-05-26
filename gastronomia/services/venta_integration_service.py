"""Integracion de cobros gastronomicos con ventas y caja central."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app import db
from app.models.caja import ColaCobro, MovimientoCaja, SesionCaja
from app.models.cliente import Cliente
from app.models.servicio import Servicio
from app.models.venta import DetalleVenta, MetodoPago, PagoVenta, Ticket, Venta
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem, GastronomiaPedidoPago


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


def crear_cola_cobro_central_desde_pedido(
    pedido: GastronomiaPedido,
    usuario_id: int,
    *,
    enviar_cocina: bool = True,
) -> ColaCobro:
    if pedido.pago:
        raise ValueError('El pedido ya fue cobrado.')
    if pedido.estado == 'cancelado':
        raise ValueError('No se puede cobrar un pedido cancelado.')

    existente = ColaCobro.query.filter(
        ColaCobro.tipo_origen == 'gastronomia',
        ColaCobro.id_origen == int(pedido.id_pedido),
        ColaCobro.estado.in_(['pendiente', 'en_proceso']),
    ).first()
    if existente:
        return existente

    metadata = {
        'gastronomia_pedido_id': int(pedido.id_pedido),
        'gastronomia_cliente_id': int(pedido.cliente_id),
        'gastronomia_enviar_cocina': bool(enviar_cocina),
        'gastronomia_codigo_entrega': pedido.codigo_entrega,
        'gastronomia_referencia_entrega': (pedido.referencia_entrega or '').strip(),
        'gastronomia_tipo_pedido': (pedido.tipo_pedido or '').strip(),
        'gastronomia_mesa': (pedido.mesa or '').strip(),
        'id_usuario_vendedor': int(pedido.usuario_id),
        'cliente_id': _consumidor_final_id(),
        'permitir_cambiar_cliente': True,
        'permitir_editar_descuento': True,
        'permitir_beneficio_fidelizacion': True,
        'observaciones': _observaciones_venta(pedido, {}),
        'items': [_item_cola_desde_pedido_item(item) for item in pedido.items.order_by(GastronomiaPedidoItem.id_item.asc()).all()],
    }
    cola = ColaCobro(
        tipo_origen='gastronomia',
        id_origen=int(pedido.id_pedido),
        id_cliente=metadata['cliente_id'],
        monto_total=Decimal(str(pedido.total or 0)).quantize(Decimal('0.01')),
        id_usuario_origen=int(usuario_id),
        estado='pendiente',
    )
    cola.set_metadata(metadata)
    db.session.add(cola)
    db.session.commit()
    return cola


def registrar_pago_gastronomia_desde_venta_central(cola_metadata: dict, venta, usuario_id: int) -> list[dict]:
    pedido_id = cola_metadata.get('gastronomia_pedido_id')
    if not pedido_id:
        return []
    pedido = GastronomiaPedido.query.filter(
        GastronomiaPedido.id_pedido == int(pedido_id),
        GastronomiaPedido.cliente_id == int(cola_metadata.get('gastronomia_cliente_id') or 0),
    ).first()
    if not pedido:
        raise ValueError('Pedido gastronomico no encontrado para registrar el cobro.')
    if pedido.pago:
        return []

    pagos = PagoVenta.query.filter_by(id_venta=venta.id_venta).order_by(PagoVenta.id_pago.asc()).all()
    movimiento = MovimientoCaja.query.filter_by(
        referencia_tipo='venta',
        referencia_id=venta.id_venta,
        tipo='ingreso',
    ).order_by(MovimientoCaja.id_movimiento_caja.asc()).first()
    metodo_unico = pagos[0].metodo if len(pagos) == 1 else None
    metodo_slug = _slug_metodo(metodo_unico) if metodo_unico else 'mixto'

    db.session.add(GastronomiaPedidoPago(
        cliente_id=int(pedido.cliente_id),
        pedido_id=int(pedido.id_pedido),
        usuario_id=int(usuario_id),
        id_sesion_caja=int(venta.id_sesion_caja),
        id_metodo_pago=int(metodo_unico.id_metodo_pago) if metodo_unico else None,
        id_venta=int(venta.id_venta),
        id_movimiento_caja=int(movimiento.id_movimiento_caja) if movimiento else None,
        metodo_pago=metodo_slug,
        subtotal=Decimal(str(pedido.total or 0)).quantize(Decimal('0.01')),
        descuento_monto=Decimal(str(venta.descuento_monto or 0)).quantize(Decimal('0.01')),
        total_cobrado=Decimal(str(venta.total or 0)).quantize(Decimal('0.01')),
        observacion=(venta.observaciones or '').strip()[:255] or None,
    ))

    eventos = [{'pedido': pedido, 'tipo': 'pedido_cobrado'}]
    if cola_metadata.get('gastronomia_enviar_cocina') and pedido.estado in {'abierto', 'enviado_cocina'}:
        pedido.estado = 'enviado_cocina'
        pedido.fecha_envio_cocina = pedido.fecha_envio_cocina or datetime.utcnow()
        eventos.append({'pedido': pedido, 'tipo': 'pedido_enviado_cocina'})
    return eventos


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


def _item_cola_desde_pedido_item(item: GastronomiaPedidoItem) -> dict:
    servicio = _servicio_para_item(item)
    precio = Decimal(str(item.precio_unitario or 0)).quantize(Decimal('0.01'))
    return {
        'tipo': 'servicio',
        'id': int(servicio.id_servicio),
        'id_servicio': int(servicio.id_servicio),
        'codigo': servicio.codigo,
        'nombre': item.nombre_producto,
        'precio': float(precio),
        'precio_base': float(precio),
        'cantidad': int(item.cantidad or 1),
        'es_servicio': True,
        'stock': 0,
        'stock_minimo': 0,
        'iva': int(servicio.porcentaje_iva or 10),
        'precio_manual': True,
    }


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
