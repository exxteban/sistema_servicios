"""Nota de crédito en papel de una devolución (sin facturación electrónica).

Sólo registra el comprobante: la devolución (`Devolucion`) sigue moviendo caja
y stock como siempre. Tabla nueva a propósito, para no agregarle columnas a
`devoluciones` (`create_all()` no las agregaría en las instalaciones que ya
existen). Una por devolución.
"""
from datetime import datetime

from app import db


class NotaCreditoPapel(db.Model):
    __tablename__ = 'notas_credito_papel'

    id = db.Column(db.Integer, primary_key=True)
    id_devolucion = db.Column(db.Integer, db.ForeignKey('devoluciones.id_devolucion', ondelete='CASCADE'),
                              nullable=False, unique=True)
    numero = db.Column(db.String(80), nullable=False)
    timbrado = db.Column(db.String(20))
    fecha = db.Column(db.Date, nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    devolucion = db.relationship('Devolucion', backref=db.backref('nota_credito_papel', uselist=False))

    def __repr__(self):
        return f'<NotaCreditoPapel {self.numero} devolución {self.id_devolucion}>'
