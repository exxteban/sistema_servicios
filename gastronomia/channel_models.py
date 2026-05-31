"""Precios alternativos del menu gastronomico por canal externo."""
from datetime import datetime

from app import db


class GastronomiaProductoPrecioCanal(db.Model):
    __tablename__ = 'gastronomia_producto_precios_canal'

    id_precio_canal = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    producto_id = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_productos.id_producto', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    canal = db.Column(db.String(30), nullable=False)
    precio = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    cliente = db.relationship('Cliente')
    producto = db.relationship(
        'GastronomiaProducto',
        backref=db.backref('precios_canal', lazy='dynamic', cascade='all, delete-orphan'),
    )

    __table_args__ = (
        db.UniqueConstraint(
            'cliente_id',
            'producto_id',
            'canal',
            name='uq_gastronomia_precio_canal_cliente_producto_canal',
        ),
    )

    def to_dict(self):
        return {
            'id_precio_canal': self.id_precio_canal,
            'cliente_id': self.cliente_id,
            'producto_id': self.producto_id,
            'canal': self.canal,
            'precio': float(self.precio or 0),
        }
