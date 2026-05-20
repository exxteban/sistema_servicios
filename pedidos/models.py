from datetime import datetime

from app import db
from pedidos.schema import ESTADO_PEDIDO_BORRADOR, ESTADOS_LABELS


class PedidoCliente(db.Model):
    __tablename__ = 'pedidos_clientes'
    __table_args__ = (
        db.Index('ix_pedidos_clientes_estado_fecha', 'estado', 'fecha_creacion'),
    )

    id_pedido = db.Column(db.Integer, primary_key=True)
    numero_pedido = db.Column(db.Integer, unique=True, index=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=False, index=True)
    id_usuario_creacion = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False, index=True)
    id_usuario_modificacion = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), index=True)
    id_venta_generada = db.Column(db.Integer, db.ForeignKey('ventas.id_venta'), index=True)
    estado = db.Column(db.String(30), nullable=False, default=ESTADO_PEDIDO_BORRADOR, index=True)
    observaciones = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    subtotal = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    descuento_monto = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    total_pagado = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    saldo_pendiente = db.Column(db.Numeric(15, 2), nullable=False, default=0)

    cliente = db.relationship('Cliente', backref='pedidos_clientes')
    usuario_creacion = db.relationship('Usuario', foreign_keys=[id_usuario_creacion])
    usuario_modificacion = db.relationship('Usuario', foreign_keys=[id_usuario_modificacion])
    venta_generada = db.relationship('Venta', foreign_keys=[id_venta_generada])
    detalles = db.relationship(
        'PedidoClienteDetalle',
        backref='pedido',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='PedidoClienteDetalle.id_detalle_pedido.asc()',
    )
    historial = db.relationship(
        'PedidoClienteHistorial',
        backref='pedido',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='desc(PedidoClienteHistorial.fecha_evento)',
    )
    pagos = db.relationship(
        'PedidoClientePago',
        backref='pedido',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='desc(PedidoClientePago.fecha_pago)',
    )

    @property
    def numero_pedido_display(self) -> str:
        numero = int(self.numero_pedido or self.id_pedido or 0)
        return f'PED-{numero:06d}' if numero > 0 else 'PED-PENDIENTE'

    @property
    def estado_label(self) -> str:
        return ESTADOS_LABELS.get(self.estado, self.estado.replace('_', ' ').title())

    def __repr__(self):
        return f'<PedidoCliente {self.id_pedido} {self.estado}>'


class PedidoClienteDetalle(db.Model):
    __tablename__ = 'pedidos_clientes_detalles'
    __table_args__ = (
        db.Index('ix_pedido_detalle_pedido_producto', 'id_pedido', 'id_producto'),
    )

    id_detalle_pedido = db.Column(db.Integer, primary_key=True)
    id_pedido = db.Column(db.Integer, db.ForeignKey('pedidos_clientes.id_pedido', ondelete='CASCADE'), nullable=False, index=True)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False, index=True)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    precio_unitario = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    porcentaje_iva = db.Column(db.Integer, nullable=False, default=10)
    subtotal = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    producto_codigo_snapshot = db.Column(db.String(50))
    producto_nombre_snapshot = db.Column(db.String(200), nullable=False)
    observaciones = db.Column(db.String(250))
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    producto = db.relationship('Producto')

    def __repr__(self):
        return f'<PedidoClienteDetalle {self.id_detalle_pedido} pedido={self.id_pedido}>'


class PedidoClienteHistorial(db.Model):
    __tablename__ = 'pedidos_clientes_historial'
    __table_args__ = (
        db.Index('ix_pedido_historial_pedido_fecha', 'id_pedido', 'fecha_evento'),
    )

    id_historial = db.Column(db.Integer, primary_key=True)
    id_pedido = db.Column(db.Integer, db.ForeignKey('pedidos_clientes.id_pedido', ondelete='CASCADE'), nullable=False, index=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True, index=True)
    tipo_evento = db.Column(db.String(50), nullable=False, index=True)
    descripcion = db.Column(db.String(255), nullable=False)
    fecha_evento = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    usuario = db.relationship('Usuario')

    def __repr__(self):
        return f'<PedidoClienteHistorial {self.id_historial} pedido={self.id_pedido}>'


class PedidoClientePago(db.Model):
    __tablename__ = 'pedidos_clientes_pagos'
    __table_args__ = (
        db.Index('ix_pedido_pago_pedido_fecha', 'id_pedido', 'fecha_pago'),
    )

    id_pago_pedido = db.Column(db.Integer, primary_key=True)
    id_pedido = db.Column(db.Integer, db.ForeignKey('pedidos_clientes.id_pedido', ondelete='CASCADE'), nullable=False, index=True)
    id_metodo_pago = db.Column(db.Integer, db.ForeignKey('metodos_pago.id_metodo_pago'), nullable=False, index=True)
    id_sesion_caja = db.Column(db.Integer, db.ForeignKey('sesiones_caja.id_sesion'), index=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False, index=True)
    id_movimiento_caja = db.Column(db.Integer, db.ForeignKey('movimientos_caja.id_movimiento_caja'), index=True)
    tipo_pago = db.Column(db.String(30), nullable=False, default='pago_parcial', index=True)
    monto = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    referencia = db.Column(db.String(100))
    observaciones = db.Column(db.Text)
    estado = db.Column(db.String(20), nullable=False, default='activo', index=True)
    fecha_pago = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    metodo = db.relationship('MetodoPago')
    sesion_caja = db.relationship('SesionCaja')
    usuario = db.relationship('Usuario')
    movimiento_caja = db.relationship('MovimientoCaja')

    def __repr__(self):
        return f'<PedidoClientePago {self.id_pago_pedido} pedido={self.id_pedido} monto={self.monto}>'
