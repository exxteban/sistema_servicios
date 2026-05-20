"""
Modelos de Inventario: Movimientos y Ajustes
"""
from datetime import datetime
from app import db


class MovimientoStock(db.Model):
    __tablename__ = 'movimientos_stock'
    
    id_movimiento = db.Column(db.Integer, primary_key=True)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False, index=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))
    
    tipo_movimiento = db.Column(db.String(20), nullable=False)  # entrada, salida, ajuste_positivo, ajuste_negativo
    cantidad = db.Column(db.Integer, nullable=False)
    stock_anterior = db.Column(db.Integer, nullable=False)
    stock_nuevo = db.Column(db.Integer, nullable=False)
    
    # Referencia al origen
    referencia_tipo = db.Column(db.String(30))  # compra, venta, devolucion, ajuste_inventario, kit_armado
    referencia_id = db.Column(db.Integer)
    
    motivo = db.Column(db.Text)
    fecha_movimiento = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relación
    usuario = db.relationship('Usuario', backref='movimientos_stock')
    
    def __repr__(self):
        return f'<MovimientoStock {self.tipo_movimiento} {self.cantidad}>'


class AjusteInventario(db.Model):
    __tablename__ = 'ajustes_inventario'
    
    id_ajuste = db.Column(db.Integer, primary_key=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    fecha_ajuste = db.Column(db.DateTime, default=datetime.utcnow)
    motivo = db.Column(db.String(100), nullable=False)  # Inventario físico, Rotura, Pérdida
    observaciones = db.Column(db.Text)
    estado = db.Column(db.String(20), default='completado')  # borrador, completado, anulado
    
    # Relaciones
    detalles = db.relationship('DetalleAjusteInventario', backref='ajuste', lazy='dynamic',
                               cascade='all, delete-orphan')
    usuario = db.relationship('Usuario', backref='ajustes_inventario')
    
    @property
    def total_diferencias(self):
        """Suma total de diferencias (positivas y negativas)"""
        return sum(d.diferencia for d in self.detalles)
    
    def __repr__(self):
        return f'<AjusteInventario {self.id_ajuste} - {self.motivo}>'


class DetalleAjusteInventario(db.Model):
    __tablename__ = 'detalle_ajustes_inventario'
    
    id_detalle_ajuste = db.Column(db.Integer, primary_key=True)
    id_ajuste = db.Column(db.Integer, db.ForeignKey('ajustes_inventario.id_ajuste', ondelete='CASCADE'), 
                          nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    stock_sistema = db.Column(db.Integer, nullable=False)
    stock_fisico = db.Column(db.Integer, nullable=False)
    diferencia = db.Column(db.Integer, nullable=False)  # stock_fisico - stock_sistema
    
    # Relación
    producto = db.relationship('Producto')
    
    def __repr__(self):
        return f'<DetalleAjuste {self.id_producto}: {self.diferencia:+d}>'
