"""Registro en caja de señas/abonos cobrados por adelantado.

Lo usan reparaciones (abono al recibir el equipo) y la agenda de peluquería/barbería
(seña del turno). La seña entra a la caja abierta del usuario que la recibe y, al cobrar
el saldo después, se descuenta: así el arqueo cuadra sin contar dos veces.
"""
from app import db
from app.models import MovimientoCaja, SesionCaja


def sesion_caja_abierta_usuario(usuario):
    """Sesión de caja abierta del usuario que opera (o None)."""
    if not usuario:
        return None
    return SesionCaja.query.filter_by(
        id_usuario=usuario.id_usuario,
        estado='abierta',
    ).first()


def registrar_movimiento_sena(*, delta, usuario, referencia_tipo, referencia_id, motivo_ingreso, motivo_egreso, mensaje_sin_caja):
    """Agrega a la caja del usuario el movimiento de una seña.

    ``delta`` > 0 es un ingreso (se recibió la seña); ``delta`` < 0 es un egreso
    (se devolvió). Devuelve ``(ok, error)``. No hace commit.
    """
    try:
        delta = float(delta or 0)
    except (TypeError, ValueError):
        delta = 0.0
    if abs(delta) < 0.005:
        return True, None

    sesion = sesion_caja_abierta_usuario(usuario)
    if not sesion:
        return False, mensaje_sin_caja

    db.session.add(MovimientoCaja(
        id_sesion_caja=sesion.id_sesion,
        id_usuario=usuario.id_usuario,
        tipo='ingreso' if delta > 0 else 'egreso',
        monto=abs(delta),
        motivo=motivo_ingreso if delta > 0 else motivo_egreso,
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
    ))
    return True, None
