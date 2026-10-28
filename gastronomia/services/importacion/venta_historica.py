"""Crea una venta pasada con la misma cadena que un cobro real de gastronomia.

Pedido entregado + item + venta central + pago + ticket + ingreso de caja, todo
fechado en el dia historico. No descuenta stock: esas ventas ya ocurrieron.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from app import db
from app.models.caja import MovimientoCaja, SesionCaja
from app.models.venta import PagoVenta, Ticket, Venta
from app.utils.helpers import get_app_timezone
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem, GastronomiaPedidoPago
from gastronomia.services.venta_integration_service import (
    _consumidor_final_id,
    _es_metodo_efectivo,
    _registrar_detalles,
    _resolver_metodo_pago,
    _slug_metodo,
)


HORA_APERTURA = time(8, 0)
HORA_PRIMERA_VENTA = time(11, 0)
HORA_CIERRE = time(23, 59)


def utc_desde_local(dia: date, hora: time, minutos_extra: int = 0) -> datetime:
    local = datetime.combine(dia, hora, tzinfo=get_app_timezone()) + timedelta(minutes=minutos_extra)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def metodo_efectivo():
    return _resolver_metodo_pago({'metodo_pago': 'efectivo'})


def abrir_sesion_historica(id_caja: int, usuario_id: int, dia: date, observacion: str) -> SesionCaja:
    sesion = SesionCaja(
        id_caja=int(id_caja),
        id_usuario=int(usuario_id),
        fecha_apertura=utc_desde_local(dia, HORA_APERTURA),
        fecha_cierre=utc_desde_local(dia, HORA_CIERRE),
        monto_inicial=Decimal('0.00'),
        estado='cerrada',
        observaciones=observacion[:500],
        id_usuario_cierre=int(usuario_id),
    )
    db.session.add(sesion)
    db.session.flush()
    return sesion


def cerrar_sesion_historica(sesion: SesionCaja, total_efectivo: Decimal) -> None:
    sesion.monto_final_sistema = total_efectivo
    sesion.monto_final_declarado = total_efectivo
    sesion.diferencia = Decimal('0.00')


def crear_venta_historica(
    *,
    cliente_id: int,
    usuario_id: int,
    sesion: SesionCaja,
    metodo,
    producto,
    fila: dict,
    fecha: datetime,
    nota_origen: str,
    nota_item: str = '',
) -> tuple[GastronomiaPedido, Venta]:
    monto = Decimal(str(fila['monto'])).quantize(Decimal('0.01'))
    cantidad = max(int(fila.get('cantidad') or 1), 1)
    pedido = GastronomiaPedido(
        cliente_id=int(cliente_id),
        usuario_id=int(usuario_id),
        tipo_pedido='mostrador',
        origen_pedido='importado',
        estado='cobrado',
        subtotal=monto,
        total=monto,
        notas=nota_origen[:1000],
        fecha_creacion=fecha,
        fecha_modificacion=fecha,
        fecha_listo=fecha,
        fecha_entrega=fecha,
    )
    db.session.add(pedido)
    db.session.flush()
    db.session.add(GastronomiaPedidoItem(
        pedido_id=pedido.id_pedido,
        cliente_id=int(cliente_id),
        producto_id=producto.id_producto,
        nombre_producto=producto.nombre,
        cantidad=cantidad,
        precio_unitario=(monto / cantidad).quantize(Decimal('0.01')),
        precio_original=(monto / cantidad).quantize(Decimal('0.01')),
        descuento_linea=Decimal('0.00'),
        notas=nota_item or None,
        subtotal=monto,
    ))
    db.session.flush()

    venta = Venta(
        id_cliente=_consumidor_final_id(),
        id_sesion_caja=sesion.id_sesion,
        id_usuario_vendedor=int(usuario_id),
        fecha_venta=fecha,
        subtotal=monto,
        descuento_monto=Decimal('0.00'),
        descuento_manual_monto=Decimal('0.00'),
        descuento_fidelizacion_monto=Decimal('0.00'),
        total=monto,
        tipo_venta='contado',
        observaciones=f'Pedido gastronomia #{pedido.id_pedido} | Importado de Excel',
    )
    db.session.add(venta)
    db.session.flush()
    venta.total_iva_10, venta.total_iva_5, venta.total_exenta = _registrar_detalles(venta, pedido)
    db.session.add(PagoVenta(id_venta=venta.id_venta, id_metodo_pago=metodo.id_metodo_pago, monto=monto, fecha_pago=fecha))

    movimiento = None
    if _es_metodo_efectivo(metodo):
        movimiento = MovimientoCaja(
            id_sesion_caja=sesion.id_sesion,
            id_usuario=int(usuario_id),
            tipo='ingreso',
            monto=monto,
            motivo=f'Cobro Efectivo Pedido Gastronomia #{pedido.id_pedido} (importado)',
            referencia_tipo='venta',
            referencia_id=venta.id_venta,
            fecha_movimiento=fecha,
        )
        db.session.add(movimiento)
    db.session.flush()
    db.session.add(Ticket(
        id_venta=venta.id_venta,
        numero_ticket=f'TK-{venta.id_venta:06d}',
        fecha_emision=fecha,
        id_usuario_emision=int(usuario_id),
    ))
    db.session.add(GastronomiaPedidoPago(
        cliente_id=int(cliente_id),
        pedido_id=pedido.id_pedido,
        usuario_id=int(usuario_id),
        id_sesion_caja=sesion.id_sesion,
        id_metodo_pago=metodo.id_metodo_pago,
        id_venta=venta.id_venta,
        id_movimiento_caja=movimiento.id_movimiento_caja if movimiento else None,
        metodo_pago=_slug_metodo(metodo),
        subtotal=monto,
        descuento_monto=Decimal('0.00'),
        total_cobrado=monto,
        observacion='Importado de Excel',
        fecha_pago=fecha,
    ))
    return pedido, venta
