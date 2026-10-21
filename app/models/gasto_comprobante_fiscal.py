"""Factura de un pago de gasto corriente, para el crédito fiscal.

El pago (`PagoGastoCorriente`) ya guarda el monto y un número de comprobante
libre, pero no lo que pide el/la contador/a para deducir el IVA: timbrado, RUC
del proveedor y tasa. Tabla nueva a propósito (`create_all()` no agregaría
columnas a `pagos_gastos_corrientes` en las instalaciones existentes). Una por
pago; el monto sale siempre del pago.
"""
from datetime import datetime

from app import db


class GastoComprobanteFiscal(db.Model):
    __tablename__ = 'gastos_comprobantes_fiscales'

    id = db.Column(db.Integer, primary_key=True)
    id_pago_gasto_corriente = db.Column(
        db.Integer, db.ForeignKey('pagos_gastos_corrientes.id_pago_gasto_corriente', ondelete='CASCADE'),
        nullable=False, unique=True,
    )
    numero = db.Column(db.String(80), nullable=False)
    timbrado = db.Column(db.String(20), nullable=False)
    ruc = db.Column(db.String(50), nullable=False)
    razon_social = db.Column(db.String(150), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    tasa_iva = db.Column(db.Integer, nullable=False, default=10)   # 10, 5 o 0 (exenta)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    pago = db.relationship('PagoGastoCorriente',
                           backref=db.backref('comprobante_fiscal', uselist=False))

    def __repr__(self):
        return f'<GastoComprobanteFiscal {self.numero} pago {self.id_pago_gasto_corriente}>'
