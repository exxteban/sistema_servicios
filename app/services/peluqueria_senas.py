"""Seña de turnos de peluquería/barbería.

La seña entra a la caja de quien la recibe (ingreso ``turno_sena``) y queda guardada en
``AgendaActividad.sena_monto``. Al cobrar el turno en el POS se aplica como descuento,
así la caja suma seña + saldo = precio, sin contar dos veces.
"""
from __future__ import annotations

from decimal import Decimal

from app.models import AgendaActividad
from app.services.caja_senas import registrar_movimiento_sena
from app.utils.helpers import formato_moneda_local

# Mismo valor que app.routes.caja.constantes.REF_SENA_TURNO (no se importa para evitar
# cargar el paquete de rutas de caja desde un servicio).
REF_SENA_TURNO = 'turno_sena'

MENSAJE_SIN_CAJA = 'Abrí tu caja para registrar la seña: el dinero tiene que entrar a la caja.'


def sena_turno(actividad) -> Decimal:
    return Decimal(str(getattr(actividad, 'sena_monto', None) or 0))


def turno_ya_cobrado(actividad) -> bool:
    asignacion = getattr(actividad, 'cliente_servicio', None)
    return bool(actividad.venta_id or (asignacion is not None and asignacion.id_venta))


def precio_turno(actividad) -> Decimal | None:
    """Precio pactado del servicio del turno, si se conoce."""
    asignacion = getattr(actividad, 'cliente_servicio', None)
    if asignacion is None or asignacion.precio_pactado is None:
        return None
    precio = Decimal(str(asignacion.precio_pactado)) * max(int(asignacion.cantidad or 1), 1)
    return precio if precio > 0 else None


def _anotar(actividad, nota):
    actividad.observaciones = '\n'.join(filter(None, [(actividad.observaciones or '').strip(), nota]))
    asignacion = getattr(actividad, 'cliente_servicio', None)
    if asignacion is not None:
        asignacion.observaciones = '\n'.join(filter(None, [(asignacion.observaciones or '').strip(), nota]))


def registrar_sena_turno(actividad, monto, usuario, nota=''):
    """Suma una seña al turno y la ingresa a caja. Devuelve ``(ok, error)``. No hace commit."""
    monto = Decimal(str(monto or 0))
    if monto <= 0:
        return False, 'Ingresa un monto de seña mayor a cero.'
    if turno_ya_cobrado(actividad):
        return False, 'Este turno ya fue cobrado; no se puede registrar una seña.'
    if (actividad.estado or '').strip().lower() == 'cancelada':
        return False, 'El turno está cancelado; no se puede registrar una seña.'

    total = sena_turno(actividad) + monto
    precio = precio_turno(actividad)
    if precio is not None and total >= precio:
        return False, f'La seña tiene que ser menor al precio del servicio ({formato_moneda_local(precio)}).'

    ok, error = registrar_movimiento_sena(
        delta=monto,
        usuario=usuario,
        referencia_tipo=REF_SENA_TURNO,
        referencia_id=actividad.id,
        motivo_ingreso=f'Seña turno #{actividad.id}',
        motivo_egreso=f'Devolución seña turno #{actividad.id}',
        mensaje_sin_caja=MENSAJE_SIN_CAJA,
    )
    if not ok:
        return False, error

    actividad.sena_monto = total
    nota = (nota or '').strip()
    _anotar(actividad, f'Seña registrada en caja: {formato_moneda_local(monto)}' + (f' - {nota}' if nota else ''))
    return True, None


def resolver_sena_al_cerrar(actividad, usuario, devolver: bool):
    """Al cancelar o marcar no-show: devuelve la seña (egreso de caja) o la deja como ingreso.

    Devuelve ``(ok, error)``. No hace commit.
    """
    sena = sena_turno(actividad)
    if sena <= 0:
        return True, None
    if not devolver:
        _anotar(actividad, f'Seña retenida: {formato_moneda_local(sena)} queda como ingreso.')
        return True, None

    ok, error = registrar_movimiento_sena(
        delta=-sena,
        usuario=usuario,
        referencia_tipo=REF_SENA_TURNO,
        referencia_id=actividad.id,
        motivo_ingreso=f'Seña turno #{actividad.id}',
        motivo_egreso=f'Devolución seña turno #{actividad.id}',
        mensaje_sin_caja='Abrí tu caja para devolver la seña: el dinero tiene que salir de la caja.',
    )
    if not ok:
        return False, error
    actividad.sena_monto = None
    _anotar(actividad, f'Seña devuelta: {formato_moneda_local(sena)} salió de caja.')
    return True, None


def sena_para_cobro(*, actividad_id=None, cliente_servicio_ids=None) -> float:
    """Seña a descontar en el POS para un turno (por id) o para servicios del cliente agendados."""
    query = AgendaActividad.query.filter(
        AgendaActividad.venta_id.is_(None),
        AgendaActividad.estado != 'cancelada',
        AgendaActividad.sena_monto.isnot(None),
    )
    if actividad_id:
        query = query.filter(AgendaActividad.id == int(actividad_id))
    elif cliente_servicio_ids:
        query = query.filter(AgendaActividad.cliente_servicio_id.in_([int(i) for i in cliente_servicio_ids]))
    else:
        return 0.0
    return float(sum((sena_turno(actividad) for actividad in query.all()), Decimal('0')))


def profesional_para_cobro(cliente_servicio_ids) -> int | None:
    """Profesional de los turnos de esos servicios del cliente, si es uno solo (será el vendedor en el POS)."""
    if not cliente_servicio_ids:
        return None
    filas = (
        AgendaActividad.query
        .with_entities(AgendaActividad.usuario_id)
        .filter(
            AgendaActividad.tipo == 'cita',
            AgendaActividad.estado != 'cancelada',
            AgendaActividad.cliente_servicio_id.in_([int(i) for i in cliente_servicio_ids]),
        )
        .distinct()
        .all()
    )
    ids = {int(fila[0]) for fila in filas if fila[0]}
    return ids.pop() if len(ids) == 1 else None
