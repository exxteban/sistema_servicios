"""Modelos de cliente final para pedidos gastronomicos publicos."""
from datetime import datetime

from app import db


class GastronomiaClienteFinal(db.Model):
    __tablename__ = 'gastronomia_clientes_finales'

    id_cliente_final = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    telefono_normalizado = db.Column(db.String(30), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    celular = db.Column(db.String(40), nullable=False)
    token_publico = db.Column(db.String(80), nullable=True, unique=True, index=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    ultima_visita = db.Column(db.DateTime)
    total_pedidos = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    cliente = db.relationship('Cliente')
    direcciones = db.relationship(
        'GastronomiaClienteDireccion',
        backref='cliente_final',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'telefono_normalizado', name='uq_gastro_cliente_final_telefono'),
    )

    def to_public_dict(self):
        return {
            'id_cliente_final': self.id_cliente_final,
            'nombre': self.nombre,
            'celular': self.celular,
            'telefono_normalizado': self.telefono_normalizado,
            'total_pedidos': int(self.total_pedidos or 0),
            'ultima_visita': self.ultima_visita.isoformat() if self.ultima_visita else None,
        }


class GastronomiaClienteDireccion(db.Model):
    __tablename__ = 'gastronomia_cliente_direcciones'

    id_direccion = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    cliente_final_id = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_clientes_finales.id_cliente_final', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    direccion = db.Column(db.String(240), nullable=False)
    referencia = db.Column(db.String(120))
    ubicacion_url = db.Column(db.String(500))
    latitud = db.Column(db.Float)
    longitud = db.Column(db.Float)
    principal = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    uso_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    fecha_ultimo_uso = db.Column(db.DateTime)

    __table_args__ = (
        db.Index('ix_gastro_dir_cliente_uso', 'cliente_id', 'cliente_final_id', 'fecha_ultimo_uso'),
    )

    def to_public_dict(self):
        return {
            'id_direccion': self.id_direccion,
            'direccion': self.direccion,
            'referencia': self.referencia,
            'ubicacion_url': self.ubicacion_url,
            'latitud': self.latitud,
            'longitud': self.longitud,
            'principal': bool(self.principal),
            'uso_count': int(self.uso_count or 0),
        }


class GastronomiaClienteFavorito(db.Model):
    __tablename__ = 'gastronomia_cliente_favoritos'

    id_favorito = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    cliente_final_id = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_clientes_finales.id_cliente_final', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    producto_id = db.Column(db.Integer, db.ForeignKey('gastronomia_productos.id_producto'), nullable=False, index=True)
    nombre_producto = db.Column(db.String(160), nullable=False)
    cantidad_pedida = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    veces_pedido = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    fecha_ultima_compra = db.Column(db.DateTime)

    producto = db.relationship('GastronomiaProducto')

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'cliente_final_id', 'producto_id', name='uq_gastro_favorito_cliente_producto'),
    )

    def to_public_dict(self):
        return {
            'producto_id': self.producto_id,
            'nombre_producto': self.nombre_producto,
            'cantidad_pedida': int(self.cantidad_pedida or 0),
            'veces_pedido': int(self.veces_pedido or 0),
            'fecha_ultima_compra': self.fecha_ultima_compra.isoformat() if self.fecha_ultima_compra else None,
        }
