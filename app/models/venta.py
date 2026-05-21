"""
Modelos de Venta, Detalle y Pagos
"""
import json
from datetime import datetime
from app import db


class MetodoPago(db.Model):
    __tablename__ = 'metodos_pago'
    
    id_metodo_pago = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    requiere_referencia = db.Column(db.Boolean, default=False)
    activo = db.Column(db.Boolean, default=True)
    orden_display = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<MetodoPago {self.nombre}>'


class Venta(db.Model):
    __tablename__ = 'ventas'
    __table_args__ = (
        db.Index('ix_ventas_estado_fecha_venta', 'estado', 'fecha_venta'),
    )
    
    id_venta = db.Column(db.Integer, primary_key=True)
    client_request_id = db.Column(db.String(64), unique=True, index=True)
    
    # Comprobante
    tipo_comprobante = db.Column(db.String(20), nullable=False, default='ticket')
    numero_comprobante = db.Column(db.String(50))
    timbrado = db.Column(db.String(20))
    
    # Relaciones principales
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=False)
    id_sesion_caja = db.Column(db.Integer, db.ForeignKey('sesiones_caja.id_sesion'), nullable=False)
    id_reparacion = db.Column(db.Integer, db.ForeignKey('reparaciones.id_reparacion'), index=True)
    id_usuario_vendedor = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), index=True)
    
    # Fecha
    fecha_venta = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Totales
    subtotal = db.Column(db.Numeric(15, 2), nullable=False)
    descuento_porcentaje = db.Column(db.Numeric(5, 2), default=0)
    descuento_monto = db.Column(db.Numeric(15, 2), default=0)
    descuento_manual_monto = db.Column(db.Numeric(15, 2), default=0)
    descuento_fidelizacion_monto = db.Column(db.Numeric(15, 2), default=0)
    beneficio_fidelizacion_tipo = db.Column(db.String(40), index=True)
    beneficio_fidelizacion_descripcion = db.Column(db.String(255))
    total_iva_10 = db.Column(db.Numeric(15, 2), default=0)
    total_iva_5 = db.Column(db.Numeric(15, 2), default=0)
    total_exenta = db.Column(db.Numeric(15, 2), default=0)
    total = db.Column(db.Numeric(15, 2), nullable=False)
    
    # Estado
    estado = db.Column(db.String(20), nullable=False, default='completada', index=True)
    tipo_venta = db.Column(db.String(20), default='contado')
    saldo_pendiente = db.Column(db.Numeric(15, 2), default=0)
    
    observaciones = db.Column(db.Text)
    
    # Relaciones
    detalles = db.relationship('DetalleVenta', backref='venta', lazy='dynamic',
                               cascade='all, delete-orphan')
    pagos = db.relationship('PagoVenta', backref='venta', lazy='dynamic',
                            cascade='all, delete-orphan')
    cuenta_por_cobrar = db.relationship('CuentaPorCobrar', backref='venta', uselist=False)
    devoluciones = db.relationship('Devolucion', backref='venta', lazy='dynamic')
    reparacion = db.relationship('Reparacion', backref=db.backref('ventas', lazy='selectin'))
    vendedor = db.relationship('Usuario', foreign_keys=[id_usuario_vendedor])
    
    @property
    def total_pagado(self):
        """Suma de todos los pagos realizados"""
        return sum(float(p.monto) for p in self.pagos)
    
    @property
    def cantidad_items(self):
        """Total de items vendidos"""
        return sum(d.cantidad for d in self.detalles)
    
    def __repr__(self):
        return f'<Venta {self.id_venta} - {self.total}>'


class DetalleVenta(db.Model):
    __tablename__ = 'detalle_ventas'
    
    id_detalle_venta = db.Column(db.Integer, primary_key=True)
    id_venta = db.Column(db.Integer, db.ForeignKey('ventas.id_venta', ondelete='CASCADE'), 
                         nullable=False, index=True)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), 
                            nullable=True, index=True)
    id_servicio = db.Column(db.Integer, db.ForeignKey('servicios.id_servicio'),
                            nullable=True, index=True)
    cantidad = db.Column(db.Integer, nullable=False)
    
    # Snapshot de precios
    precio_unitario = db.Column(db.Numeric(15, 2), nullable=False)
    precio_original = db.Column(db.Numeric(15, 2), nullable=False)
    
    # Impuestos
    porcentaje_iva = db.Column(db.Integer, nullable=False)
    monto_iva = db.Column(db.Numeric(15, 2), nullable=False)
    
    # Totales
    descuento_linea = db.Column(db.Numeric(15, 2), default=0)
    subtotal = db.Column(db.Numeric(15, 2), nullable=False)
    
    es_kit = db.Column(db.Boolean, default=False)
    
    # Relación al producto
    producto = db.relationship('Producto')
    servicio = db.relationship('Servicio')

    @property
    def item_nombre(self):
        if self.producto:
            return self.producto.nombre
        if self.servicio:
            return self.servicio.nombre
        return 'Item'

    @property
    def item_codigo(self):
        if self.producto:
            return self.producto.codigo
        if self.servicio:
            return self.servicio.codigo or f'SRV-{self.servicio.id_servicio}'
        return ''

    @property
    def es_servicio_detalle(self):
        return bool(self.servicio or (self.producto and self.producto.es_servicio))
    
    def __repr__(self):
        item_id = self.id_producto if self.id_producto is not None else f'S{self.id_servicio}'
        return f'<DetalleVenta {item_id} x{self.cantidad}>'


class PagoVenta(db.Model):
    __tablename__ = 'pagos_ventas'
    
    id_pago = db.Column(db.Integer, primary_key=True)
    id_venta = db.Column(db.Integer, db.ForeignKey('ventas.id_venta', ondelete='CASCADE'), 
                         nullable=False, index=True)
    id_metodo_pago = db.Column(db.Integer, db.ForeignKey('metodos_pago.id_metodo_pago'), 
                               nullable=False)
    monto = db.Column(db.Numeric(15, 2), nullable=False)
    referencia = db.Column(db.String(100))
    fecha_pago = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relación
    metodo = db.relationship('MetodoPago')
    
    def __repr__(self):
        return f'<PagoVenta {self.monto} - {self.metodo.nombre if self.metodo else "?"}>'


class CuentaPorCobrar(db.Model):
    __tablename__ = 'cuentas_por_cobrar'

    id_cuenta_cobrar = db.Column(db.Integer, primary_key=True)
    id_venta = db.Column(db.Integer, db.ForeignKey('ventas.id_venta'), nullable=False, index=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=False, index=True)
    monto_total = db.Column(db.Numeric(15, 2), nullable=False)
    monto_cobrado = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    saldo_pendiente = db.Column(db.Numeric(15, 2), nullable=False)
    fecha_vencimiento = db.Column(db.Date)
    estado = db.Column(db.String(20), nullable=False, default='pendiente')
    dias_vencido = db.Column(db.Integer, default=0)

    cliente = db.relationship('Cliente')
    pagos = db.relationship('PagoCuentaCobrar', backref='cuenta', lazy='dynamic',
                            cascade='all, delete-orphan')

    def __repr__(self):
        return f'<CuentaPorCobrar {self.id_cuenta_cobrar} - {self.estado}>'


class PagoCuentaCobrar(db.Model):
    __tablename__ = 'pagos_cuentas_cobrar'

    id_pago_cuenta = db.Column(db.Integer, primary_key=True)
    id_cuenta_cobrar = db.Column(db.Integer, db.ForeignKey('cuentas_por_cobrar.id_cuenta_cobrar'),
                                 nullable=False, index=True)
    id_sesion_caja = db.Column(db.Integer, db.ForeignKey('sesiones_caja.id_sesion'), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    monto = db.Column(db.Numeric(15, 2), nullable=False)
    id_metodo_pago = db.Column(db.Integer, db.ForeignKey('metodos_pago.id_metodo_pago'), nullable=False)
    referencia = db.Column(db.String(100))
    fecha_pago = db.Column(db.DateTime, default=datetime.utcnow)
    observaciones = db.Column(db.Text)
    cliente_nombre_snapshot = db.Column(db.String(150))
    id_cuota_credito_principal = db.Column(
        db.Integer,
        db.ForeignKey('cuotas_credito_venta.id_cuota_credito'),
        index=True,
    )
    numero_cuota_principal = db.Column(db.Integer)
    detalle_aplicacion_json = db.Column(db.Text)
    estado = db.Column(db.String(20), nullable=False, default='activo', index=True)
    fecha_anulacion = db.Column(db.DateTime)
    id_usuario_anulacion = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))
    motivo_anulacion = db.Column(db.Text)
    id_movimiento_reversa = db.Column(db.Integer, db.ForeignKey('movimientos_caja.id_movimiento_caja'))

    metodo = db.relationship('MetodoPago')
    sesion_caja = db.relationship('SesionCaja')
    usuario = db.relationship('Usuario', foreign_keys=[id_usuario])
    usuario_anulacion = db.relationship('Usuario', foreign_keys=[id_usuario_anulacion])
    movimiento_reversa = db.relationship('MovimientoCaja', foreign_keys=[id_movimiento_reversa])
    cuota_principal = db.relationship('CuotaCreditoVenta', foreign_keys=[id_cuota_credito_principal])

    def esta_anulado(self):
        return (self.estado or '').strip().lower() == 'anulado'

    def get_detalle_aplicacion(self):
        try:
            if not self.detalle_aplicacion_json:
                return {}
            return json.loads(self.detalle_aplicacion_json)
        except Exception:
            return {}

    def set_detalle_aplicacion(self, data):
        try:
            self.detalle_aplicacion_json = json.dumps(data or {}, ensure_ascii=False)
        except Exception:
            self.detalle_aplicacion_json = '{}'

    def __repr__(self):
        return f'<PagoCuentaCobrar {self.monto}>'


class Ticket(db.Model):
    """Registro de emisión y reimpresiones de tickets para auditoría"""
    __tablename__ = 'tickets'
    
    id_ticket = db.Column(db.Integer, primary_key=True)
    id_venta = db.Column(db.Integer, db.ForeignKey('ventas.id_venta'), nullable=False, index=True)
    numero_ticket = db.Column(db.String(20), unique=True, nullable=False)  # Ej: "TK-000010"
    fecha_emision = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_ultima_impresion = db.Column(db.DateTime)
    cantidad_impresiones = db.Column(db.Integer, default=1)
    formato = db.Column(db.String(30), default='thermal_80mm')
    id_usuario_emision = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))
    
    # Relaciones
    venta = db.relationship('Venta', backref=db.backref('ticket', uselist=False))
    usuario_emision = db.relationship('Usuario')
    
    def __repr__(self):
        return f'<Ticket {self.numero_ticket} - Impresiones: {self.cantidad_impresiones}>'
