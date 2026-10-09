"""Bloqueo compartido hasta commit/rollback para operaciones sobre una caja.

Un UPDATE sin cambio toma un bloqueo de escritura también en SQLite, donde
SELECT FOR UPDATE no bloquea. Debe ejecutarse antes de leer importes o pagos.
"""
from app import db
from app.models import SesionCaja


def bloquear_sesion_caja(id_sesion):
    SesionCaja.query.filter_by(id_sesion=id_sesion).update(
        {SesionCaja.estado: SesionCaja.estado}, synchronize_session=False,
    )
    return SesionCaja.query.populate_existing().filter_by(id_sesion=id_sesion).first()


def bloquear_caja_de_venta(venta):
    sesion = bloquear_sesion_caja(venta.id_sesion_caja)
    db.session.refresh(venta)
    db.session.expire(venta, ['pagos', 'devoluciones', 'cuenta_por_cobrar'])
    return sesion
