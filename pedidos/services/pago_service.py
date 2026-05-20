from datetime import datetime
from decimal import Decimal

from app import db
from app.models import MetodoPago, MovimientoCaja, SesionCaja
from pedidos.models import PedidoCliente, PedidoClientePago
from pedidos.schema import (
    ESTADO_PEDIDO_BORRADOR,
    ESTADO_PEDIDO_CANCELADO,
    ESTADO_PEDIDO_EN_PREPARACION,
    ESTADO_PEDIDO_PAGADO,
    ESTADO_PEDIDO_PAGO_PARCIAL,
    ESTADO_PEDIDO_PENDIENTE_SENA,
)
from pedidos.services.pedido_service import _clean_text, _to_decimal, recalcular_totales_pedido, registrar_historial

TIPO_PAGO_SENA = 'sena'
TIPO_PAGO_PARCIAL = 'pago_parcial'
TIPO_PAGO_TOTAL = 'pago_total'

TIPOS_PAGO_PEDIDO = (
    TIPO_PAGO_SENA,
    TIPO_PAGO_PARCIAL,
    TIPO_PAGO_TOTAL,
)

TIPOS_PAGO_LABELS = {
    TIPO_PAGO_SENA: 'Sena',
    TIPO_PAGO_PARCIAL: 'Pago parcial',
    TIPO_PAGO_TOTAL: 'Pago total',
}


def listar_metodos_pago_activos():
    metodos = (
        MetodoPago.query.filter_by(activo=True)
        .order_by(MetodoPago.orden_display.asc(), MetodoPago.nombre.asc())
        .all()
    )
    return [metodo for metodo in metodos if not _es_metodo_credito_tienda(getattr(metodo, 'nombre', ''))]


def label_tipo_pago(tipo_pago: str) -> str:
    return TIPOS_PAGO_LABELS.get((tipo_pago or '').strip(), (tipo_pago or '').replace('_', ' ').title())


def _resolver_metodo_pago(id_metodo_pago: int | None):
    if not id_metodo_pago:
        return None
    return MetodoPago.query.filter_by(id_metodo_pago=id_metodo_pago, activo=True).first()


def _es_metodo_efectivo(nombre: str) -> bool:
    """Delegado canonico: usa `app.services.caja_metodos.es_metodo_efectivo`."""
    from app.services.caja_metodos import es_metodo_efectivo as _svc_es_efectivo
    return _svc_es_efectivo(nombre)


def _es_metodo_credito_tienda(nombre: str) -> bool:
    return ' '.join((nombre or '').strip().lower().split()) in {'credito tienda', 'venta a credito'}


def _resolver_estado_post_pago(pedido: PedidoCliente, tipo_pago: str) -> str:
    total = _to_decimal(pedido.total)
    total_pagado = _to_decimal(pedido.total_pagado)
    saldo = _to_decimal(pedido.saldo_pendiente)
    estado_actual = (pedido.estado or '').strip() or ESTADO_PEDIDO_BORRADOR

    if total <= 0:
        return estado_actual
    if saldo <= Decimal('0.00'):
        return ESTADO_PEDIDO_PAGADO
    if total_pagado > 0:
        if tipo_pago == TIPO_PAGO_SENA and estado_actual in {ESTADO_PEDIDO_BORRADOR, ESTADO_PEDIDO_PENDIENTE_SENA}:
            return ESTADO_PEDIDO_EN_PREPARACION
        return ESTADO_PEDIDO_PAGO_PARCIAL
    return ESTADO_PEDIDO_PENDIENTE_SENA


def registrar_pago_pedido(
    pedido: PedidoCliente,
    *,
    id_metodo_pago: int,
    monto,
    tipo_pago: str,
    id_usuario: int,
    referencia: str = '',
    observaciones: str = '',
    fecha_pago: datetime | None = None,
    sesion: SesionCaja | None = None,
):
    if (pedido.estado or '').strip() == ESTADO_PEDIDO_CANCELADO:
        raise ValueError('No se pueden registrar pagos en un pedido cancelado.')

    tipo_pago = (tipo_pago or '').strip()
    if tipo_pago not in TIPOS_PAGO_PEDIDO:
        raise ValueError('Tipo de pago invalido.')

    metodo = _resolver_metodo_pago(id_metodo_pago)
    if not metodo:
        raise ValueError('Debe seleccionar un metodo de pago valido.')
    if _es_metodo_credito_tienda(getattr(metodo, 'nombre', '')):
        raise ValueError('No se puede registrar un cobro usando Credito Tienda.')

    referencia_limpia = _clean_text(referencia, 100)
    if getattr(metodo, 'requiere_referencia', False) and not referencia_limpia:
        raise ValueError(f'El metodo de pago {metodo.nombre} requiere referencia.')

    monto_decimal = _to_decimal(monto)
    if monto_decimal <= 0:
        raise ValueError('El monto del pago debe ser mayor a cero.')

    sesion_abierta = sesion
    if sesion_abierta is not None and int(getattr(sesion_abierta, 'id_sesion', 0) or 0) <= 0:
        sesion_abierta = None
    if sesion_abierta is None and _es_metodo_efectivo(getattr(metodo, 'nombre', '')):
        sesion_abierta = SesionCaja.query.filter_by(id_usuario=id_usuario, estado='abierta').first()
        if sesion_abierta is None:
            raise ValueError('No hay caja abierta para registrar un pago en efectivo.')

    total = _to_decimal(pedido.total)
    saldo_antes = _to_decimal(pedido.saldo_pendiente)
    if total <= 0:
        raise ValueError('El pedido no tiene total a cobrar.')
    if saldo_antes <= 0:
        raise ValueError('El pedido ya no tiene saldo pendiente.')
    if monto_decimal > saldo_antes:
        raise ValueError('El monto no puede superar el saldo pendiente.')

    if tipo_pago == TIPO_PAGO_TOTAL:
        saldo_resultante = (saldo_antes - monto_decimal).quantize(Decimal('0.01'))
        if saldo_resultante != Decimal('0.00'):
            raise ValueError('El pago total debe cancelar por completo el saldo pendiente.')

    pago = PedidoClientePago(
        id_pedido=pedido.id_pedido,
        id_metodo_pago=metodo.id_metodo_pago,
        id_sesion_caja=int(sesion_abierta.id_sesion) if sesion_abierta is not None else None,
        id_usuario=id_usuario,
        tipo_pago=tipo_pago,
        monto=monto_decimal.quantize(Decimal('0.01')),
        referencia=referencia_limpia or None,
        observaciones=(observaciones or '').strip() or None,
        fecha_pago=fecha_pago or datetime.utcnow(),
        estado='activo',
    )
    db.session.add(pago)
    db.session.flush()

    movimiento = None
    if sesion_abierta is not None and _es_metodo_efectivo(getattr(metodo, 'nombre', '')):
        movimiento = MovimientoCaja(
            id_sesion_caja=int(sesion_abierta.id_sesion),
            id_usuario=int(id_usuario),
            tipo='ingreso',
            monto=pago.monto,
            motivo=f'Cobro Pedido {pedido.numero_pedido_display}',
            referencia_tipo='pago_pedido',
            referencia_id=int(pago.id_pago_pedido),
            fecha_movimiento=pago.fecha_pago,
        )
        db.session.add(movimiento)
        db.session.flush()
        pago.id_movimiento_caja = int(movimiento.id_movimiento_caja)

    recalcular_totales_pedido(pedido)
    pedido.estado = _resolver_estado_post_pago(pedido, tipo_pago)
    pedido.id_usuario_modificacion = id_usuario

    descripcion = (
        f'Se registro {label_tipo_pago(tipo_pago).lower()} de Gs. '
        f'{format(float(pago.monto or 0), ",.0f").replace(",", ".")} via {metodo.nombre}.'
    )
    registrar_historial(pedido, descripcion, 'pago_registrado', id_usuario=id_usuario)
    return {
        'pago': pago,
        'pedido': pedido,
        'metodo': metodo,
        'sesion': sesion_abierta,
        'movimiento_caja': movimiento,
    }
