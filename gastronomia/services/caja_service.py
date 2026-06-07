"""Cobro de pedidos gastronomicos."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError

from app import db
from app.utils.auditoria_utils import registrar_auditoria
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoPago
from gastronomia.services.pedido_service import obtener_pedido, registrar_evento_pedido
from gastronomia.services.venta_integration_service import (
    cerrar_colas_activas_gastronomia_pedido,
    crear_venta_central_desde_pedido,
)


METODOS_PAGO = {'efectivo', 'tarjeta', 'transferencia', 'qr', 'mixto'}
ESTADOS_COBRABLES = {'abierto', 'enviado_cocina', 'preparando', 'listo', 'entregado'}
# Pedidos que todavia estan en curso: es normal que existan al cerrar turno.
ESTADOS_EN_CURSO = {'abierto', 'enviado_cocina', 'preparando'}
# Pedidos cuyo producto ya salio pero siguen sin cobrar: requieren atencion al cerrar.
ESTADOS_TERMINADOS_SIN_COBRO = {'listo', 'entregado'}


def _query_pedidos_caja(cliente_id: int):
    return (
        GastronomiaPedido.query
        .outerjoin(GastronomiaPedidoPago, GastronomiaPedidoPago.pedido_id == GastronomiaPedido.id_pedido)
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.estado.in_(ESTADOS_COBRABLES),
            GastronomiaPedidoPago.id_pago.is_(None),
        )
    )


def listar_pedidos_caja(cliente_id: int) -> list[GastronomiaPedido]:
    return (
        _query_pedidos_caja(cliente_id)
        .order_by(GastronomiaPedido.fecha_creacion.desc(), GastronomiaPedido.id_pedido.desc())
        .all()
    )


def contar_pedidos_caja(cliente_id: int) -> int:
    return _query_pedidos_caja(cliente_id).count()


def resumen_pedidos_impagos_para_cierre(cliente_id: int) -> dict:
    """Agrupa los pedidos cobrables sin pago para advertir al cerrar caja.

    Devuelve dos grupos:
    - ``en_curso``: pedidos legitimos en proceso (aviso informativo, no bloquea).
    - ``terminados``: producto ya entregado/listo sin cobrar (confirmacion explicita).
    """
    pedidos = (
        _query_pedidos_caja(cliente_id)
        .order_by(GastronomiaPedido.fecha_creacion.asc(), GastronomiaPedido.id_pedido.asc())
        .all()
    )

    en_curso: list[dict] = []
    terminados: list[dict] = []
    total_en_curso = Decimal('0.00')
    total_terminados = Decimal('0.00')

    for pedido in pedidos:
        monto = Decimal(str(pedido.total or 0)).quantize(Decimal('0.01'))
        item = {
            'id_pedido': pedido.id_pedido,
            'codigo_entrega': pedido.codigo_entrega,
            'estado': pedido.estado,
            'tipo_pedido': pedido.tipo_pedido,
            'mesa': (pedido.mesa or '').strip(),
            'nombre_cliente': (pedido.nombre_cliente or '').strip(),
            'total': float(monto),
        }
        if pedido.estado in ESTADOS_TERMINADOS_SIN_COBRO:
            terminados.append(item)
            total_terminados += monto
        else:
            en_curso.append(item)
            total_en_curso += monto

    return {
        'en_curso': en_curso,
        'terminados': terminados,
        'total_en_curso': float(total_en_curso),
        'total_terminados': float(total_terminados),
        'hay_terminados': bool(terminados),
        'hay_en_curso': bool(en_curso),
    }


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

    _actualizar_costo_envio_si_corresponde(pedido, data)
    subtotal = Decimal(str(pedido.total or 0)).quantize(Decimal('0.01'))
    descuento = _parse_decimal(data.get('descuento_monto'), Decimal('0.00'))
    if descuento < 0:
        raise ValueError('El descuento no puede ser negativo.')
    if descuento > subtotal:
        raise ValueError('El descuento no puede superar el total del pedido.')

    pago = _reservar_pago_pedido(cliente_id, usuario_id, pedido, metodo_pago, subtotal, descuento, data)

    try:
        integracion = crear_venta_central_desde_pedido(
            pedido,
            usuario_id,
            data,
            descuento=descuento,
        )
    except ValueError:
        db.session.rollback()
        raise
    venta = integracion['venta']
    sesion = integracion['sesion']
    metodo = integracion['metodo']
    movimiento = integracion['movimiento']

    pago.id_sesion_caja = int(sesion.id_sesion)
    pago.id_metodo_pago = int(metodo.id_metodo_pago)
    pago.id_venta = int(venta.id_venta)
    pago.id_movimiento_caja = int(movimiento.id_movimiento_caja) if movimiento else None
    pago.metodo_pago = integracion['metodo_slug'] or metodo_pago
    cerrar_colas_activas_gastronomia_pedido(pedido, venta, usuario_id)
    registrar_auditoria(
        accion='cobrar_pedido_gastronomia',
        modulo='gastronomia',
        descripcion=f'Cobro de pedido gastronomico #{pedido.id_pedido} como venta #{venta.id_venta}',
        referencia_tipo='gastronomia_pedido',
        referencia_id=int(pedido.id_pedido),
        datos_nuevos={
            'id_venta': int(venta.id_venta),
            'id_sesion_caja': int(sesion.id_sesion),
            'id_metodo_pago': int(metodo.id_metodo_pago),
            'total_cobrado': float(subtotal - descuento),
        },
        commit=False,
    )
    db.session.commit()
    registrar_evento_pedido(pedido, 'pedido_cobrado')
    return pedido


def _reservar_pago_pedido(
    cliente_id: int,
    usuario_id: int,
    pedido: GastronomiaPedido,
    metodo_pago: str,
    subtotal: Decimal,
    descuento: Decimal,
    data: dict,
) -> GastronomiaPedidoPago:
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
    db.session.add(pago)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise ValueError('El pedido ya fue cobrado.')
    return pago


def _actualizar_costo_envio_si_corresponde(pedido: GastronomiaPedido, data: dict) -> None:
    if (pedido.tipo_pedido or '').strip().lower() != 'delivery' or 'costo_envio' not in data:
        return
    costo_envio = _parse_decimal(data.get('costo_envio'), Decimal('0.00'))
    if costo_envio < 0:
        raise ValueError('El costo de envio no puede ser negativo.')
    pedido.costo_envio = costo_envio
    pedido.total = Decimal(str(pedido.subtotal or 0)).quantize(Decimal('0.01')) + costo_envio


def _parse_decimal(value, default: Decimal) -> Decimal:
    if value in (None, ''):
        return default
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Monto invalido.')
