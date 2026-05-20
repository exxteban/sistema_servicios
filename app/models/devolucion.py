"""
Modelos de Devolución
"""
from datetime import datetime
from app import db


class Devolucion(db.Model):
    __tablename__ = 'devoluciones'
    
    id_devolucion = db.Column(db.Integer, primary_key=True)
    id_venta = db.Column(db.Integer, db.ForeignKey('ventas.id_venta'), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    id_sesion_caja = db.Column(db.Integer, db.ForeignKey('sesiones_caja.id_sesion'), nullable=False)
    
    fecha_devolucion = db.Column(db.DateTime, default=datetime.utcnow)
    motivo = db.Column(db.String(100), nullable=False)
    accion_stock = db.Column(db.String(20), nullable=False)  # retorno_stock, descarte, ninguna
    monto_total = db.Column(db.Numeric(15, 2), nullable=False)
    metodo_reembolso = db.Column(db.String(50), nullable=False, default='efectivo')
    estado = db.Column(db.String(20), default='completada')
    observaciones = db.Column(db.Text)
    
    # Relaciones
    detalles = db.relationship('DetalleDevolucion', backref='devolucion', lazy='dynamic',
                               cascade='all, delete-orphan')
    usuario = db.relationship('Usuario', backref='devoluciones')
    sesion_caja = db.relationship('SesionCaja', backref='devoluciones')
    
    def __repr__(self):
        return f'<Devolucion {self.id_devolucion} - Venta {self.id_venta}>'


class DetalleDevolucion(db.Model):
    __tablename__ = 'detalle_devoluciones'
    
    id_detalle_devolucion = db.Column(db.Integer, primary_key=True)
    id_devolucion = db.Column(db.Integer, db.ForeignKey('devoluciones.id_devolucion', ondelete='CASCADE'), 
                              nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    id_detalle_venta_original = db.Column(db.Integer, db.ForeignKey('detalle_ventas.id_detalle_venta'))
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Numeric(15, 2), nullable=False)
    subtotal = db.Column(db.Numeric(15, 2), nullable=False)
    
    # Relación
    producto = db.relationship('Producto')
    detalle_venta_original = db.relationship('DetalleVenta')
    
    def __repr__(self):
        return f'<DetalleDevolucion {self.id_producto} x{self.cantidad}>'
