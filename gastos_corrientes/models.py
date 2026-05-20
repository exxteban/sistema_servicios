from datetime import datetime
from decimal import Decimal

from app import db


class GastoCorriente(db.Model):
    __tablename__ = 'gastos_corrientes'

    id_gasto_corriente = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=True, index=True)
    nombre = db.Column(db.String(120), nullable=False, index=True)
    categoria = db.Column(db.String(30), nullable=False, default='otros', index=True)
    descripcion = db.Column(db.Text, nullable=True)
    monto_estimado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    dia_vencimiento = db.Column(db.Integer, nullable=False, default=1)
    activo = db.Column(db.Boolean, nullable=False, default=True, index=True)
    requiere_caja_por_defecto = db.Column(db.Boolean, nullable=False, default=True)
    alerta_activa = db.Column(db.Boolean, nullable=False, default=True)
    dias_anticipacion_alerta = db.Column(db.Integer, nullable=False, default=3)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_actualizacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    pagos = db.relationship(
        'PagoGastoCorriente',
        backref='gasto_corriente',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='desc(PagoGastoCorriente.periodo_anio), desc(PagoGastoCorriente.periodo_mes), desc(PagoGastoCorriente.id_pago_gasto_corriente)',
    )

    __table_args__ = (
        db.Index('ix_gastos_corrientes_cliente_activo', 'cliente_id', 'activo'),
    )

    def monto_estimado_decimal(self) -> Decimal:
        return Decimal(self.monto_estimado or 0)

    def dia_vencimiento_int(self) -> int:
        return int(self.dia_vencimiento or 1)

    def dias_anticipacion_alerta_int(self) -> int:
        return int(self.dias_anticipacion_alerta or 0)

    def __repr__(self):
        return f'<GastoCorriente {self.id_gasto_corriente} {self.nombre}>'


class PagoGastoCorriente(db.Model):
    __tablename__ = 'pagos_gastos_corrientes'

    id_pago_gasto_corriente = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=True, index=True)
    id_gasto_corriente = db.Column(
        db.Integer,
        db.ForeignKey('gastos_corrientes.id_gasto_corriente', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    periodo_anio = db.Column(db.Integer, nullable=False, index=True)
    periodo_mes = db.Column(db.Integer, nullable=False, index=True)
    fecha_vencimiento = db.Column(db.Date, nullable=False, index=True)
    fecha_pago = db.Column(db.Date, nullable=True, index=True)
    monto_estimado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    monto_pagado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    estado = db.Column(db.String(20), nullable=False, default='pendiente', index=True)
    pagado_desde_caja = db.Column(db.Boolean, nullable=False, default=False)
    id_sesion_caja = db.Column(
        db.Integer,
        db.ForeignKey('sesiones_caja.id_sesion'),
        nullable=True,
        index=True,
    )
    id_movimiento_caja = db.Column(
        db.Integer,
        db.ForeignKey('movimientos_caja.id_movimiento_caja'),
        nullable=True,
        index=True,
    )
    id_movimiento_reversa = db.Column(
        db.Integer,
        db.ForeignKey('movimientos_caja.id_movimiento_caja'),
        nullable=True,
        index=True,
    )
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True, index=True)
    id_usuario_anulacion = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True, index=True)
    observacion = db.Column(db.Text, nullable=True)
    numero_comprobante = db.Column(db.String(120), nullable=True)
    comprobante_adjunto_path = db.Column(db.String(255), nullable=True)
    comprobante_adjunto_nombre = db.Column(db.String(255), nullable=True)
    comprobante_adjunto_mime = db.Column(db.String(120), nullable=True)
    motivo_anulacion = db.Column(db.Text, nullable=True)
    fecha_anulacion = db.Column(db.Date, nullable=True, index=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_actualizacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    sesion_caja = db.relationship('SesionCaja', foreign_keys=[id_sesion_caja])
    movimiento_caja = db.relationship('MovimientoCaja', foreign_keys=[id_movimiento_caja])
    movimiento_reversa = db.relationship('MovimientoCaja', foreign_keys=[id_movimiento_reversa])
    usuario = db.relationship('Usuario', foreign_keys=[id_usuario])
    usuario_anulacion = db.relationship('Usuario', foreign_keys=[id_usuario_anulacion])

    __table_args__ = (
        db.Index(
            'ix_pago_gasto_periodo_gasto_estado',
            'id_gasto_corriente',
            'periodo_anio',
            'periodo_mes',
            'estado',
        ),
    )

    @property
    def periodo(self) -> str:
        return f'{int(self.periodo_anio):04d}-{int(self.periodo_mes):02d}'

    def monto_estimado_decimal(self) -> Decimal:
        return Decimal(self.monto_estimado or 0)

    def monto_pagado_decimal(self) -> Decimal:
        return Decimal(self.monto_pagado or 0)

    def esta_anulado(self) -> bool:
        return (self.estado or '').strip().lower() == 'anulado'

    def tiene_comprobante_adjunto(self) -> bool:
        return bool((self.comprobante_adjunto_path or '').strip())

    def __repr__(self):
        return f'<PagoGastoCorriente {self.id_pago_gasto_corriente} gasto={self.id_gasto_corriente} periodo={self.periodo}>'
