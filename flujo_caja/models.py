from datetime import datetime
from decimal import Decimal

from app import db


class FlujoCajaSemana(db.Model):
    __tablename__ = 'flujo_caja_semanas'

    id_flujo_semana = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=True, index=True, default=0)
    fecha_inicio = db.Column(db.Date, nullable=False, index=True)
    fecha_fin = db.Column(db.Date, nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=True)
    saldo_inicial_estimado = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    estado = db.Column(db.String(20), nullable=False, default='abierta', index=True)
    notas = db.Column(db.Text, nullable=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_actualizacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    movimientos = db.relationship(
        'FlujoCajaMovimiento',
        backref='semana',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='FlujoCajaMovimiento.fecha.asc(), FlujoCajaMovimiento.id_flujo_movimiento.asc()',
    )

    __table_args__ = (
        db.Index('ix_flujo_semana_cliente_fecha', 'cliente_id', 'fecha_inicio'),
        db.UniqueConstraint('cliente_id', 'fecha_inicio', name='uq_flujo_semana_cliente_fecha'),
    )

    def saldo_inicial_decimal(self) -> Decimal:
        return Decimal(self.saldo_inicial_estimado or 0)

    def __repr__(self):
        return f'<FlujoCajaSemana {self.id_flujo_semana} {self.fecha_inicio}>'


class FlujoCajaMovimiento(db.Model):
    __tablename__ = 'flujo_caja_movimientos'

    id_flujo_movimiento = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=True, index=True, default=0)
    id_flujo_semana = db.Column(
        db.Integer,
        db.ForeignKey('flujo_caja_semanas.id_flujo_semana', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    fecha = db.Column(db.Date, nullable=False, index=True)
    tipo = db.Column(db.String(12), nullable=False, index=True)
    categoria = db.Column(db.String(40), nullable=False, default='otros', index=True)
    concepto = db.Column(db.String(160), nullable=False)
    monto_estimado = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    monto_real = db.Column(db.Numeric(14, 2), nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='estimado', index=True)
    origen = db.Column(db.String(40), nullable=False, default='manual', index=True)
    notas = db.Column(db.Text, nullable=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True, index=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_actualizacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    usuario = db.relationship('Usuario', foreign_keys=[id_usuario])

    __table_args__ = (
        db.Index('ix_flujo_mov_cliente_semana_estado', 'cliente_id', 'id_flujo_semana', 'estado'),
    )

    def monto_estimado_decimal(self) -> Decimal:
        return Decimal(self.monto_estimado or 0)

    def monto_real_decimal(self) -> Decimal:
        return Decimal(self.monto_real or 0)

    def monto_operativo_decimal(self) -> Decimal:
        return self.monto_real_decimal() if self.estado == 'realizado' and self.monto_real is not None else self.monto_estimado_decimal()

    def __repr__(self):
        return f'<FlujoCajaMovimiento {self.id_flujo_movimiento} {self.tipo} {self.concepto}>'


class FlujoCajaPlantilla(db.Model):
    __tablename__ = 'flujo_caja_plantillas'

    id_flujo_plantilla = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=True, index=True, default=0)
    nombre = db.Column(db.String(120), nullable=False)
    tipo = db.Column(db.String(12), nullable=False, index=True)
    categoria = db.Column(db.String(40), nullable=False, default='otros')
    concepto = db.Column(db.String(160), nullable=False)
    monto_estimado = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    dia_semana = db.Column(db.Integer, nullable=False, default=0)
    activa = db.Column(db.Boolean, nullable=False, default=True, index=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_actualizacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        db.Index('ix_flujo_plantilla_cliente_activa', 'cliente_id', 'activa'),
    )

    def monto_estimado_decimal(self) -> Decimal:
        return Decimal(self.monto_estimado or 0)

    def __repr__(self):
        return f'<FlujoCajaPlantilla {self.id_flujo_plantilla} {self.nombre}>'
