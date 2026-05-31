"""Modelos aislados para recetas y trazabilidad de stock gastronomico."""
from datetime import datetime

from app import db


class GastronomiaRecetaInsumo(db.Model):
    __tablename__ = 'gastronomia_receta_insumos'

    id_receta_insumo = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('gastronomia_productos.id_producto', ondelete='CASCADE'), nullable=False, index=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False, index=True)
    cantidad = db.Column(db.Integer, nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    insumo = db.relationship('Producto')

    __table_args__ = (
        db.UniqueConstraint('producto_id', 'insumo_id', name='uq_gastronomia_receta_producto_insumo'),
        db.CheckConstraint('cantidad > 0', name='ck_gastronomia_receta_cantidad_positiva'),
    )

    def to_dict(self):
        return {
            'id_receta_insumo': self.id_receta_insumo,
            'producto_id': self.producto_id,
            'insumo_id': self.insumo_id,
            'insumo_nombre': self.insumo.nombre if self.insumo else '',
            'cantidad': int(self.cantidad or 0),
            'unidad_stock': getattr(self.insumo, 'unidad_stock', 'unidad') or 'unidad',
        }


class GastronomiaOpcionInsumo(db.Model):
    __tablename__ = 'gastronomia_opcion_insumos'

    id_opcion_insumo = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    opcion_id = db.Column(db.Integer, db.ForeignKey('gastronomia_opciones_producto.id_opcion', ondelete='CASCADE'), nullable=False, index=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False, index=True)
    cantidad_delta = db.Column(db.Integer, nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    insumo = db.relationship('Producto')

    __table_args__ = (
        db.UniqueConstraint('opcion_id', 'insumo_id', name='uq_gastronomia_opcion_insumo'),
    )

    def to_dict(self):
        return {
            'id_opcion_insumo': self.id_opcion_insumo,
            'opcion_id': self.opcion_id,
            'insumo_id': self.insumo_id,
            'insumo_nombre': self.insumo.nombre if self.insumo else '',
            'cantidad_delta': int(self.cantidad_delta or 0),
            'unidad_stock': getattr(self.insumo, 'unidad_stock', 'unidad') or 'unidad',
        }


class GastronomiaPedidoItemConsumo(db.Model):
    __tablename__ = 'gastronomia_pedido_item_consumos'

    id_consumo = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey('gastronomia_pedido_items.id_item', ondelete='CASCADE'), nullable=False, index=True)
    insumo_id = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=True, index=True)
    tipo_origen = db.Column(db.String(30), nullable=False)
    nombre_stock = db.Column(db.String(200), nullable=False)
    unidad_stock = db.Column(db.String(20), nullable=False, default='unidad')
    cantidad = db.Column(db.Integer, nullable=False)
    stock_anterior = db.Column(db.Integer, nullable=False)
    stock_nuevo = db.Column(db.Integer, nullable=False)
    faltante = db.Column(db.Integer, nullable=False, default=0)
    restaurado = db.Column(db.Boolean, nullable=False, default=False, index=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_restauracion = db.Column(db.DateTime)

    insumo = db.relationship('Producto')

    def alerta_dict(self):
        return {
            'id_consumo': self.id_consumo,
            'item_id': self.item_id,
            'insumo_id': self.insumo_id,
            'tipo_origen': self.tipo_origen,
            'nombre': self.nombre_stock,
            'unidad_stock': self.unidad_stock,
            'cantidad': int(self.cantidad or 0),
            'stock_anterior': int(self.stock_anterior or 0),
            'stock_nuevo': int(self.stock_nuevo or 0),
            'faltante': int(self.faltante or 0),
            'mensaje': (
                f'Stock insuficiente de {self.nombre_stock}: se requieren {self.cantidad} '
                f'{self.unidad_stock}, habia {self.stock_anterior} y queda {self.stock_nuevo}.'
            ),
        }
