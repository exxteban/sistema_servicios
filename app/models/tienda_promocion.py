"""
Modelos de promociones de tienda.
Cada promoción queda aislada por cliente y puede aplicarse a varios productos.
"""
from datetime import datetime

from app import db


PROMOTION_TYPES = (
    'porcentaje',
    'monto_fijo',
    'precio_promocional',
    'cantidad',
)


class TiendaPromocion(db.Model):
    __tablename__ = 'tienda_promociones'

    id_promocion = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    nombre = db.Column(db.String(160), nullable=False)
    descripcion_corta = db.Column(db.Text, nullable=True)
    tipo = db.Column(db.String(30), nullable=False, default='porcentaje', server_default='porcentaje')
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    cantidad_lleva = db.Column(db.Integer, nullable=True)
    cantidad_paga = db.Column(db.Integer, nullable=True)
    fecha_inicio = db.Column(db.DateTime, nullable=False, index=True)
    fecha_fin = db.Column(db.DateTime, nullable=False, index=True)
    activa = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_modificacion = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    cliente = db.relationship('Cliente', backref='promociones_tienda', lazy='select')
    productos_rel = db.relationship(
        'TiendaPromocionProducto',
        backref='promocion',
        lazy='selectin',
        cascade='all, delete-orphan',
    )
    gastronomia_productos_rel = db.relationship(
        'TiendaPromocionGastronomiaProducto',
        backref='promocion',
        lazy='selectin',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        db.Index('ix_tienda_promociones_cliente_estado_fecha', 'id_cliente', 'activa', 'fecha_inicio', 'fecha_fin'),
    )

    def is_active_now(self, now: datetime | None = None) -> bool:
        now = now or datetime.utcnow()
        return bool(self.activa and self.fecha_inicio <= now <= self.fecha_fin)

    def __repr__(self):
        return f'<TiendaPromocion id={self.id_promocion} cliente={self.id_cliente} {self.nombre}>'


class TiendaPromocionProducto(db.Model):
    __tablename__ = 'tienda_promocion_productos'

    id_relacion = db.Column(db.Integer, primary_key=True)
    id_promocion = db.Column(
        db.Integer,
        db.ForeignKey('tienda_promociones.id_promocion', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    id_producto = db.Column(
        db.Integer,
        db.ForeignKey('productos.id_producto', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    producto = db.relationship('Producto', backref='promociones_tienda_rel', lazy='select')

    __table_args__ = (
        db.UniqueConstraint('id_promocion', 'id_producto', name='uq_tienda_promocion_producto'),
        db.Index('ix_tienda_promocion_productos_producto_promocion', 'id_producto', 'id_promocion'),
    )

    def __repr__(self):
        return f'<TiendaPromocionProducto promo={self.id_promocion} producto={self.id_producto}>'


class TiendaPromocionGastronomiaProducto(db.Model):
    __tablename__ = 'tienda_promocion_gastronomia_productos'

    id_relacion = db.Column(db.Integer, primary_key=True)
    id_promocion = db.Column(
        db.Integer,
        db.ForeignKey('tienda_promociones.id_promocion', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    id_producto = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_productos.id_producto', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    producto = db.relationship('GastronomiaProducto', backref='promociones_tienda_rel', lazy='select')

    __table_args__ = (
        db.UniqueConstraint('id_promocion', 'id_producto', name='uq_tienda_promocion_gastronomia_producto'),
        db.Index('ix_tienda_promocion_gastro_producto_promocion', 'id_producto', 'id_promocion'),
    )

    def __repr__(self):
        return f'<TiendaPromocionGastronomiaProducto promo={self.id_promocion} producto={self.id_producto}>'
