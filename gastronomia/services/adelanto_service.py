"""Sena (adelanto) de encargos: cobro, devolucion, retencion y cancelacion.

Reglas (docs/pasteleria_fase1_diseno.md, puntos B y D):
- La sena exige caja abierta del operador. Solo la sena en efectivo crea un
  `MovimientoCaja` (el arqueo suma todo ingreso de caja sin mirar el metodo).
- Al cancelar con sena vigente el operador elige: devolver todo, retener todo o
  retener una parte. Retener no crea movimientos: el dinero ya esta en caja.
- La sena debe ser menor que el total del encargo.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from app import db
from app.models import Usuario
from app.services.caja_senas import crear_movimiento_sena, sesion_caja_abierta_usuario
from app.utils.auditoria_utils import registrar_auditoria
from gastronomia.config_flags import (
    OPCION_DEVOLVER_TODO,
    OPCION_RETENER_PARCIAL,
    OPCION_RETENER_TODO,
)
from gastronomia.encargo_models import (
    ADELANTO_APLICADO,
    ADELANTO_DEVUELTO,
    ADELANTO_RETENIDO,
    ADELANTO_VIGENTE,
    GastronomiaPedidoAdelanto,
)
from gastronomia.models import GastronomiaPedido
from gastronomia.services.encargo_service import exigir_encargos_habilitados
from gastronomia.services.pasteleria_flags import parametros_encargos
from gastronomia.services.pedido_service import cambiar_estado_pedido, registrar_evento_pedido
from gastronomia.services.venta_integration_service import _es_metodo_efectivo, _resolver_metodo_pago, _slug_metodo


# Mismo valor que usaria app.routes.caja.constantes (no se importa para no cargar rutas desde un servicio).
REF_SENA_ENCARGO = 'gastronomia_sena'
MENSAJE_SIN_CAJA = 'Abri tu caja para registrar la sena: el dinero tiene que entrar a la caja.'
MENSAJE_SIN_CAJA_RESOLVER = 'Abri tu caja para resolver la sena: el dinero tiene que salir de la caja.'
ESTADOS_QUE_ADMITEN_SENA = {'abierto', 'enviado_cocina', 'preparando', 'listo'}
CENTAVOS = Decimal('0.01')


def adelantos_pedido(pedido: GastronomiaPedido, *, estado: str | None = None) -> list[GastronomiaPedidoAdelanto]:
    consulta = pedido.adelantos
    if estado:
        consulta = consulta.filter_by(estado=estado)
    return consulta.order_by(GastronomiaPedidoAdelanto.id_adelanto.asc()).all()


def sena_vigente(pedido: GastronomiaPedido) -> Decimal:
    return _sumar(adelanto.monto for adelanto in adelantos_pedido(pedido, estado=ADELANTO_VIGENTE))


def resumen_sena(pedido: GastronomiaPedido) -> dict:
    """Totales de seña de un encargo (los usa el tablero, nunca la cocina)."""
    adelantos = adelantos_pedido(pedido)
    vigente = _sumar(a.monto for a in adelantos if a.estado == ADELANTO_VIGENTE)
    total = Decimal(str(pedido.total or 0))
    return {
        'sena_vigente': float(vigente),
        'sena_total_cobrada': float(_sumar(a.monto for a in adelantos if a.estado != ADELANTO_DEVUELTO)),
        'saldo': float(max(total - vigente, Decimal('0'))),
        'adelantos': [a.to_dict() for a in adelantos],
    }


def registrar_adelanto(cliente_id: int, usuario_id: int, pedido_id: int, data: dict) -> GastronomiaPedidoAdelanto:
    exigir_encargos_habilitados(cliente_id)
    pedido = _encargo_bloqueado(cliente_id, pedido_id)
    if pedido.pago or pedido.estado not in ESTADOS_QUE_ADMITEN_SENA:
        raise ValueError('Este encargo ya no admite senas.')
    monto = _parse_monto(data.get('monto'))
    if monto <= 0:
        raise ValueError('Ingresa un monto de sena mayor a cero.')
    if sena_vigente(pedido) + monto >= Decimal(str(pedido.total or 0)):
        raise ValueError('La sena tiene que ser menor al total del encargo. Para cobrar todo, usa la caja.')

    usuario = _usuario(usuario_id)
    sesion = sesion_caja_abierta_usuario(usuario)
    if not sesion:
        raise ValueError(MENSAJE_SIN_CAJA)
    metodo = _resolver_metodo_pago(data)

    movimiento = None
    if _es_metodo_efectivo(metodo):
        movimiento, error = crear_movimiento_sena(
            delta=monto,
            usuario=usuario,
            referencia_tipo=REF_SENA_ENCARGO,
            referencia_id=int(pedido.id_pedido),
            motivo_ingreso=f'Sena encargo #{pedido.id_pedido}',
            motivo_egreso=f'Devolucion sena encargo #{pedido.id_pedido}',
            mensaje_sin_caja=MENSAJE_SIN_CAJA,
        )
        if error:
            raise ValueError(error)
        db.session.flush()

    adelanto = GastronomiaPedidoAdelanto(
        cliente_id=int(cliente_id),
        pedido_id=int(pedido.id_pedido),
        usuario_id=int(usuario_id),
        id_sesion_caja=int(sesion.id_sesion),
        id_movimiento_caja=int(movimiento.id_movimiento_caja) if movimiento else None,
        id_metodo_pago=int(metodo.id_metodo_pago),
        metodo_pago=_slug_metodo(metodo),
        referencia=(data.get('referencia') or '').strip()[:100] or None,
        monto=monto,
        observacion=(data.get('observacion') or '').strip()[:255] or None,
    )
    db.session.add(adelanto)
    db.session.flush()
    registrar_auditoria(
        accion='registrar_sena_encargo',
        modulo='gastronomia',
        descripcion=f'Sena de encargo #{pedido.id_pedido}',
        referencia_tipo='gastronomia_pedido',
        referencia_id=int(pedido.id_pedido),
        datos_nuevos={'id_adelanto': int(adelanto.id_adelanto), 'monto': float(monto), 'metodo': adelanto.metodo_pago},
        commit=False,
    )
    db.session.commit()
    registrar_evento_pedido(pedido, 'encargo_sena_registrada')
    return adelanto


def cancelar_encargo(
    cliente_id: int,
    usuario_id: int,
    pedido_id: int,
    *,
    opcion: str | None = None,
    monto_retenido=None,
    motivo: str = '',
) -> GastronomiaPedido:
    """Cancela un encargo resolviendo antes la sena en una sola transaccion.

    No exige el flag: si el local apaga los encargos con senas cobradas, el
    dinero no puede quedar atrapado.
    """
    pedido = _encargo_bloqueado(cliente_id, pedido_id)
    if pedido.pago:
        raise ValueError('No se puede cancelar un encargo ya cobrado. Anula la venta primero.')

    adelantos = adelantos_pedido(pedido, estado=ADELANTO_VIGENTE)
    ya_cancelado = pedido.estado == 'cancelado'
    if ya_cancelado and not adelantos:
        raise ValueError('El encargo ya esta cancelado.')
    try:
        if adelantos:
            _resolver_adelantos(
                cliente_id, usuario_id, pedido, adelantos,
                opcion=opcion, monto_retenido=monto_retenido, motivo=motivo,
            )
        if ya_cancelado:
            # Venta anulada: el pedido ya estaba cancelado y solo faltaba decidir la sena.
            db.session.commit()
        else:
            cambiar_estado_pedido(cliente_id, pedido_id, 'cancelado', sena_resuelta=True)
    except ValueError:
        db.session.rollback()
        raise
    return pedido


def _resolver_adelantos(cliente_id, usuario_id, pedido, adelantos, *, opcion, monto_retenido, motivo) -> None:
    permitidas = parametros_encargos(cliente_id)['opciones_cancelacion']
    if opcion not in permitidas:
        raise ValueError('Elegi que hacer con la sena: ' + ', '.join(permitidas).replace('_', ' ') + '.')

    total = _sumar(a.monto for a in adelantos)
    retenido = _monto_a_retener(opcion, total, monto_retenido)
    usuario = _usuario(usuario_id)
    sesion = sesion_caja_abierta_usuario(usuario)
    if not sesion:
        raise ValueError(MENSAJE_SIN_CAJA_RESOLVER)

    # Reparte la retencion en orden cronologico; lo no retenido se devuelve.
    por_retener = retenido
    reparto = []
    for adelanto in adelantos:
        retiene = min(Decimal(str(adelanto.monto)), por_retener)
        por_retener -= retiene
        reparto.append((adelanto, retiene, Decimal(str(adelanto.monto)) - retiene))

    efectivo_a_devolver = _sumar(devuelve for adelanto, _, devuelve in reparto if adelanto.id_movimiento_caja)
    movimiento = None
    if efectivo_a_devolver > 0:
        movimiento, error = crear_movimiento_sena(
            delta=-efectivo_a_devolver,
            usuario=usuario,
            referencia_tipo=REF_SENA_ENCARGO,
            referencia_id=int(pedido.id_pedido),
            motivo_ingreso=f'Sena encargo #{pedido.id_pedido}',
            motivo_egreso=f'Devolucion sena encargo #{pedido.id_pedido}',
            mensaje_sin_caja=MENSAJE_SIN_CAJA_RESOLVER,
        )
        if error:
            raise ValueError(error)
        db.session.flush()

    ahora = datetime.utcnow()
    nota = (motivo or '').strip()[:200]
    for adelanto, retiene, devuelve in reparto:
        adelanto.estado = ADELANTO_RETENIDO if retiene > 0 else ADELANTO_DEVUELTO
        adelanto.monto_devuelto = devuelve
        if movimiento is not None and devuelve > 0 and adelanto.id_movimiento_caja:
            adelanto.id_movimiento_devolucion = int(movimiento.id_movimiento_caja)
        adelanto.fecha_resolucion = ahora
        adelanto.id_sesion_resolucion = int(sesion.id_sesion)
        adelanto.usuario_resolucion_id = int(usuario_id)
        if nota:
            adelanto.observacion = nota
    registrar_auditoria(
        accion='cancelar_encargo_con_sena',
        modulo='gastronomia',
        descripcion=f'Cancelacion de encargo #{pedido.id_pedido}: {opcion.replace("_", " ")}',
        referencia_tipo='gastronomia_pedido',
        referencia_id=int(pedido.id_pedido),
        datos_nuevos={'opcion': opcion, 'retenido': float(retenido), 'devuelto': float(total - retenido)},
        commit=False,
    )
    db.session.flush()


def _monto_a_retener(opcion: str, total: Decimal, monto_retenido) -> Decimal:
    if opcion == OPCION_DEVOLVER_TODO:
        return Decimal('0.00')
    if opcion == OPCION_RETENER_TODO:
        return total
    if opcion == OPCION_RETENER_PARCIAL:
        retenido = _parse_monto(monto_retenido)
        if retenido <= 0 or retenido >= total:
            raise ValueError('El monto a retener tiene que ser mayor a cero y menor a la sena cobrada.')
        return retenido
    raise ValueError('Opcion de sena invalida.')


def aplicar_adelantos(pedido: GastronomiaPedido, id_venta: int) -> Decimal:
    """Marca como aplicados los adelantos vigentes al cobrar el saldo. Devuelve el total aplicado."""
    adelantos = adelantos_pedido(pedido, estado=ADELANTO_VIGENTE)
    for adelanto in adelantos:
        adelanto.estado = ADELANTO_APLICADO
        adelanto.id_venta = int(id_venta)
    return _sumar(adelanto.monto for adelanto in adelantos)


def revertir_adelantos_aplicados(pedido: GastronomiaPedido) -> None:
    """Si se anula la venta, la sena vuelve a quedar pendiente de decision."""
    for adelanto in adelantos_pedido(pedido, estado=ADELANTO_APLICADO):
        adelanto.estado = ADELANTO_VIGENTE
        adelanto.id_venta = None


def _encargo_bloqueado(cliente_id: int, pedido_id: int) -> GastronomiaPedido:
    pedido = (
        GastronomiaPedido.query
        .populate_existing()
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.id_pedido == int(pedido_id),
            GastronomiaPedido.es_encargo.is_(True),
        )
        .with_for_update()
        .first()
    )
    if not pedido:
        raise ValueError('Encargo no encontrado.')
    return pedido


def _usuario(usuario_id: int) -> Usuario:
    usuario = db.session.get(Usuario, int(usuario_id))
    if not usuario:
        raise ValueError('Usuario no encontrado.')
    return usuario


def _parse_monto(valor) -> Decimal:
    try:
        return Decimal(str(valor if valor not in (None, '') else 0)).quantize(CENTAVOS)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Monto invalido.')


def _sumar(valores) -> Decimal:
    return sum((Decimal(str(valor or 0)) for valor in valores), Decimal('0.00'))
