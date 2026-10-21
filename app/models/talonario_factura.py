"""Talonario de facturas en papel (preimpresas o autoimpresor).

Sólo para instalaciones sin facturación electrónica: con SIFEN el timbrado
y la numeración los maneja `facturacion_electronica`. Tabla nueva a
propósito: `create_all()` la crea en las instalaciones existentes, y
`Venta.timbrado` (que ya existía) guarda el timbrado de cada venta.
"""
from datetime import datetime

from app import db


class TalonarioFactura(db.Model):
    __tablename__ = 'talonarios_factura'

    id = db.Column(db.Integer, primary_key=True)
    timbrado = db.Column(db.String(20), nullable=False)
    vigencia_desde = db.Column(db.Date, nullable=False)
    vigencia_hasta = db.Column(db.Date, nullable=False)
    establecimiento = db.Column(db.String(3), nullable=False)
    punto_expedicion = db.Column(db.String(3), nullable=False)
    numero_desde = db.Column(db.Integer, nullable=False, default=1)
    numero_hasta = db.Column(db.Integer, nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def prefijo(self):
        return f'{self.establecimiento}-{self.punto_expedicion}-'

    def __repr__(self):
        return f'<TalonarioFactura {self.timbrado} {self.prefijo}>'
