"""Presentaciones de compra convertibles a la unidad base de inventario."""
from datetime import datetime

from app import db


class ProductoPresentacionStock(db.Model):
    __tablename__ = 'producto_presentaciones_stock'

    id_presentacion = db.Column(db.Integer, primary_key=True)
    id_producto = db.Column(
        db.Integer,
        db.ForeignKey('productos.id_producto', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    nombre = db.Column(db.String(100), nullable=False)
    factor_unidad_base = db.Column(db.Integer, nullable=False, default=1)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    producto = db.relationship(
        'Producto',
        backref=db.backref('presentaciones_stock', lazy='dynamic', cascade='all, delete-orphan'),
    )

    __table_args__ = (
        db.UniqueConstraint('id_producto', 'nombre', name='uq_producto_presentacion_stock_nombre'),
        db.CheckConstraint('factor_unidad_base > 0', name='ck_producto_presentacion_factor_positivo'),
    )

    def to_dict(self):
        return {
            'id_presentacion': self.id_presentacion,
            'id_producto': self.id_producto,
            'nombre': self.nombre,
            'factor_unidad_base': int(self.factor_unidad_base or 1),
            'activo': bool(self.activo),
        }
