"""
Modelo de Cliente
"""
from datetime import datetime
from app import db


class Cliente(db.Model):
    __tablename__ = 'clientes'
    
    id_cliente = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False, index=True)
    ruc_ci = db.Column(db.String(50), index=True)
    telefono = db.Column(db.String(50))
    email = db.Column(db.String(100))
    direccion = db.Column(db.Text)
    tipo = db.Column(db.String(20), nullable=False, default='minorista')
    nivel_estrellas = db.Column(db.Integer, nullable=False, default=3)
    fidelizacion_compras_acumuladas = db.Column(db.Integer, nullable=False, default=0)
    fidelizacion_consumos_disponibles = db.Column(db.Integer, nullable=False, default=0)
    fidelizacion_consumos_canjeados = db.Column(db.Integer, nullable=False, default=0)
    limite_credito = db.Column(db.Numeric(15, 2), default=0)
    saldo_pendiente = db.Column(db.Numeric(15, 2), default=0)
    notas = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    ventas = db.relationship('Venta', backref='cliente', lazy='dynamic')
    observaciones = db.relationship(
        'ClienteObservacion',
        backref='cliente',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='desc(ClienteObservacion.fecha_observacion)'
    )
    fidelizacion_movimientos = db.relationship(
        'ClienteFidelizacionMovimiento',
        backref='cliente',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='desc(ClienteFidelizacionMovimiento.fecha_movimiento)'
    )
    
    @property
    def es_consumidor_final(self):
        """Retorna True si es el cliente genérico"""
        return self.id_cliente == 1
    
    @property
    def es_mayorista(self):
        return self.tipo == 'mayorista'
    
    @property
    def credito_disponible(self):
        """Crédito disponible para compras"""
        return float(self.limite_credito or 0) - float(self.saldo_pendiente or 0)

    @property
    def nivel_estrellas_seguro(self):
        try:
            nivel = int(self.nivel_estrellas or 0)
        except (TypeError, ValueError):
            nivel = 3
        return max(1, min(5, nivel))

    @property
    def fidelizacion_compras_acumuladas_seguras(self):
        try:
            return int(self.fidelizacion_compras_acumuladas or 0)
        except (TypeError, ValueError):
            return 0

    @property
    def fidelizacion_consumos_disponibles_seguro(self):
        try:
            return int(self.fidelizacion_consumos_disponibles or 0)
        except (TypeError, ValueError):
            return 0

    @property
    def fidelizacion_consumos_canjeados_seguro(self):
        try:
            return int(self.fidelizacion_consumos_canjeados or 0)
        except (TypeError, ValueError):
            return 0
    
    def __repr__(self):
        return f'<Cliente {self.nombre}>'


class ClienteObservacion(db.Model):
    __tablename__ = 'cliente_observaciones'

    id_observacion = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True, index=True)
    observacion = db.Column(db.Text, nullable=False)
    fecha_observacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    usuario = db.relationship('Usuario')

    def __repr__(self):
        return f'<ClienteObservacion {self.id_observacion} cliente={self.id_cliente}>'
