"""Anulacion operativa de ventas gastronomicas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app import db
from app.models import MovimientoCaja, PagoVenta, Venta
from app.services.caja_metodos import obtener_metodo_efectivo_id
from app.services.clientes_fidelizacion import revertir_fidelizacion_por_anulacion_venta
from app.utils.auditoria_utils import registrar_auditoria
from gastronomia.models import GastronomiaPedido
from gastronomia.services.pedido_service import registrar_evento_pedido
from gastronomia.services.venta_integration_service import registrar_anulacion_gastronomia_desde_venta_central


def anular_venta_gastronomica(
    cliente_id: int,
    pedido_id: int,
    usuario_id: int,
    *,
    motivo: str | None = None,
    id_autorizacion: int | None = None,
) -> GastronomiaPedido:
    pedido = GastronomiaPedido.query.filter_by(
        cliente_id=int(cliente_id),
        id_pedido=int(pedido_id),
    ).first()
    if not pedido:
        raise ValueError('Pedido no encontrado.')
    if not pedido.pago or not pedido.pago.id_venta:
        raise ValueError('El pedido no tiene una venta cobrada para anular.')

    venta = db.session.get(Venta, int(pedido.pago.id_venta))
    if not venta:
        raise ValueError('Venta central no encontrada.')
    if (venta.estado or '').strip().lower() == 'anulada':
        raise ValueError('La venta ya esta anulada.')
    sesion = getattr(venta, 'sesion_caja', None)
    if sesion is not None and (sesion.estado or '').strip().lower() == 'cerrada':
        raise ValueError('No se puede anular una venta cuya sesion de caja ya esta cerrada.')

    _registrar_reverso_caja(venta, usuario_id)
    revertir_fidelizacion_por_anulacion_venta(venta, id_usuario=usuario_id)
    venta.estado = 'anulada'
    if motivo:
        observaciones = (venta.observaciones or '').strip()
        marca = f'Anulacion gastronomia: {motivo.strip()[:240]}'
        venta.observaciones = f'{observaciones} | {marca}'.strip(' |')

    eventos = registrar_anulacion_gastronomia_desde_venta_central(venta, usuario_id)
    db.session.commit()

    for evento in eventos:
        registrar_evento_pedido(evento['pedido'], evento['tipo'])
    registrar_auditoria(
        accion='anular_venta',
        modulo='ventas',
        descripcion=_descripcion_auditoria(venta.id_venta, pedido.id_pedido, motivo),
        referencia_tipo='venta',
        referencia_id=venta.id_venta,
        id_autorizacion=id_autorizacion,
    )
    return pedido


def _registrar_reverso_caja(venta: Venta, usuario_id: int) -> None:
    movimientos = (
        MovimientoCaja.query
        .filter_by(
            id_sesion_caja=venta.id_sesion_caja,
            referencia_tipo='venta',
            referencia_id=venta.id_venta,
        )
        .order_by(MovimientoCaja.id_movimiento_caja.asc())
        .all()
    )
    if movimientos:
        for movimiento in movimientos:
            _agregar_movimiento_reverso(movimiento, venta.id_venta, usuario_id)
        return

    efectivo_id = obtener_metodo_efectivo_id(solo_activos=False)
    if efectivo_id is None:
        return
    total_efectivo = (
        db.session.query(db.func.sum(PagoVenta.monto))
        .filter(PagoVenta.id_venta == venta.id_venta, PagoVenta.id_metodo_pago == efectivo_id)
        .scalar()
    )
    if total_efectivo and Decimal(str(total_efectivo)) > 0:
        db.session.add(MovimientoCaja(
            id_sesion_caja=venta.id_sesion_caja,
            id_usuario=int(usuario_id),
            tipo='egreso',
            monto=total_efectivo,
            motivo=_motivo_reverso(venta.id_venta, 'ajuste efectivo'),
            referencia_tipo='anulacion_venta',
            referencia_id=venta.id_venta,
            fecha_movimiento=datetime.utcnow(),
        ))


def _agregar_movimiento_reverso(movimiento: MovimientoCaja, venta_id: int, usuario_id: int) -> None:
    tipo_original = (movimiento.tipo or '').strip().lower()
    if tipo_original not in {'ingreso', 'egreso'}:
        return
    db.session.add(MovimientoCaja(
        id_sesion_caja=movimiento.id_sesion_caja,
        id_usuario=int(usuario_id),
        tipo='egreso' if tipo_original == 'ingreso' else 'ingreso',
        monto=movimiento.monto,
        motivo=_motivo_reverso(venta_id, movimiento.motivo),
        referencia_tipo='anulacion_venta',
        referencia_id=venta_id,
        fecha_movimiento=datetime.utcnow(),
    ))


def _motivo_reverso(venta_id: int, detalle: str | None) -> str:
    motivo = f'Anulacion venta #{venta_id}: {(detalle or "").strip()}'.strip()
    return motivo[:200] or f'Anulacion venta #{venta_id}'


def _descripcion_auditoria(venta_id: int, pedido_id: int, motivo: str | None) -> str:
    descripcion = f'Anulacion venta gastronomia #{venta_id} desde pedido #{pedido_id}'
    if motivo:
        descripcion = f'{descripcion}: {motivo.strip()[:180]}'
    return descripcion
