"""
Modelos de Compra y Detalle
"""
from datetime import datetime, date
from app import db


class Compra(db.Model):
    __tablename__ = 'compras'
    
    id_compra = db.Column(db.Integer, primary_key=True)
    numero_factura = db.Column(db.String(50))
    timbrado = db.Column(db.String(20))
    id_proveedor = db.Column(db.Integer, db.ForeignKey('proveedores.id_proveedor'), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    fecha_compra = db.Column(db.Date, nullable=False, default=date.today, index=True)
    hora_compra = db.Column(db.Time)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_vencimiento = db.Column(db.Date)
    factura_imagen_url = db.Column(db.String(500))
    
    # Totales
    subtotal = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    total_iva_10 = db.Column(db.Numeric(15, 2), default=0)
    total_iva_5 = db.Column(db.Numeric(15, 2), default=0)
    total = db.Column(db.Numeric(15, 2), nullable=False)
    
    # Estado
    estado = db.Column(db.String(20), nullable=False, default='completada')
    tipo_compra = db.Column(db.String(20), default='contado')
    pagada = db.Column(db.Boolean, default=False)
    es_resumida = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    
    observaciones = db.Column(db.Text)
    
    # Relaciones
    detalles = db.relationship('DetalleCompra', backref='compra', lazy='dynamic',
                               cascade='all, delete-orphan')
    pagos = db.relationship('PagoCompra', backref='compra', lazy='dynamic',
                            cascade='all, delete-orphan')
    cuenta_por_pagar = db.relationship('CuentaPorPagar', backref='compra', uselist=False)
    usuario = db.relationship('Usuario', backref='compras')
    
    @property
    def cantidad_items(self):
        return sum(d.cantidad for d in self.detalles)
    
    def __repr__(self):
        return f'<Compra {self.id_compra} - {self.total}>'


class DetalleCompra(db.Model):
    __tablename__ = 'detalle_compras'
    
    id_detalle_compra = db.Column(db.Integer, primary_key=True)
    id_compra = db.Column(db.Integer, db.ForeignKey('compras.id_compra', ondelete='CASCADE'), 
                          nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Numeric(15, 2), nullable=False)
    porcentaje_iva = db.Column(db.Integer, nullable=False, default=10)
    subtotal = db.Column(db.Numeric(15, 2), nullable=False)
    
    # Relación
    producto = db.relationship('Producto')
    
    def __repr__(self):
        return f'<DetalleCompra {self.id_producto} x{self.cantidad}>'


class PagoCompra(db.Model):
    __tablename__ = 'pagos_compras'

    id_pago_compra = db.Column(db.Integer, primary_key=True)
    id_compra = db.Column(db.Integer, db.ForeignKey('compras.id_compra', ondelete='CASCADE'),
                          nullable=False, index=True)
    id_metodo_pago = db.Column(db.Integer, db.ForeignKey('metodos_pago.id_metodo_pago'),
                               nullable=False)
    id_sesion_caja = db.Column(db.Integer, db.ForeignKey('sesiones_caja.id_sesion'))
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    monto = db.Column(db.Numeric(15, 2), nullable=False)
    referencia = db.Column(db.String(100))
    fecha_pago = db.Column(db.DateTime, default=datetime.utcnow)
    observaciones = db.Column(db.Text)

    metodo = db.relationship('MetodoPago')
    sesion_caja = db.relationship('SesionCaja')
    usuario = db.relationship('Usuario')

    def __repr__(self):
        return f'<PagoCompra {self.monto}>'


class CuentaPorPagar(db.Model):
    __tablename__ = 'cuentas_por_pagar'

    id_cuenta_pagar = db.Column(db.Integer, primary_key=True)
    id_compra = db.Column(db.Integer, db.ForeignKey('compras.id_compra'), nullable=False, index=True)
    id_proveedor = db.Column(db.Integer, db.ForeignKey('proveedores.id_proveedor'), nullable=False, index=True)
    monto_total = db.Column(db.Numeric(15, 2), nullable=False)
    monto_pagado = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    saldo_pendiente = db.Column(db.Numeric(15, 2), nullable=False)
    fecha_vencimiento = db.Column(db.Date)
    estado = db.Column(db.String(20), nullable=False, default='pendiente')
    dias_vencido = db.Column(db.Integer, default=0)

    proveedor = db.relationship('Proveedor')

    def __repr__(self):
        return f'<CuentaPorPagar {self.id_cuenta_pagar} - {self.estado}>'
