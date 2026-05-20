"""
Modelo de Proveedor
"""
from datetime import datetime
from app import db


class Proveedor(db.Model):
    __tablename__ = 'proveedores'
    
    id_proveedor = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    ruc = db.Column(db.String(50), unique=True)
    telefono = db.Column(db.String(50))
    email = db.Column(db.String(100))
    direccion = db.Column(db.Text)
    contacto_nombre = db.Column(db.String(100))
    contacto_telefono = db.Column(db.String(50))
    dias_credito = db.Column(db.Integer, default=0)
    notas = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    compras = db.relationship('Compra', backref='proveedor', lazy='dynamic')
    productos = db.relationship('Producto', backref='proveedor_principal', lazy='dynamic')
    
    def __repr__(self):
        return f'<Proveedor {self.nombre}>'
