from datetime import datetime

from app import db
from app.models.venta import CuentaPorCobrar, PagoCuentaCobrar


class PlanCreditoVenta(db.Model):
    __tablename__ = 'planes_credito_venta'
    __table_args__ = (
        db.Index('ix_planes_credito_venta_cuenta_estado', 'id_cuenta_cobrar', 'estado'),
    )

    id_plan_credito_venta = db.Column(db.Integer, primary_key=True)
    id_cuenta_cobrar = db.Column(
        db.Integer,
        db.ForeignKey('cuentas_por_cobrar.id_cuenta_cobrar', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    modo = db.Column(db.String(20), nullable=False, default='cuotas')
    cantidad_cuotas = db.Column(db.Integer, nullable=False)
    frecuencia_dias = db.Column(db.Integer, nullable=False, default=30)
    fecha_primer_vencimiento = db.Column(db.Date, nullable=False)
    monto_total_financiado = db.Column(db.Numeric(15, 2), nullable=False)
    tasa_periodica_pct = db.Column(db.Numeric(8, 4), nullable=False, default=0)
    sistema_amortizacion = db.Column(db.String(20), nullable=False, default='frances')
    monto_total_interes = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    monto_total_con_interes = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    monto_anticipo = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    monto_cobrado = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    saldo_pendiente = db.Column(db.Numeric(15, 2), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='pendiente', index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    id_plan_anterior = db.Column(
        db.Integer,
        db.ForeignKey('planes_credito_venta.id_plan_credito_venta'),
        index=True,
    )
    motivo_refinanciacion = db.Column(db.Text)
    es_refinanciacion = db.Column(db.Boolean, default=False)

    cuenta = db.relationship(
        'CuentaPorCobrar',
        backref=db.backref('planes_credito', lazy='dynamic', cascade='all, delete-orphan'),
    )
    plan_anterior = db.relationship(
        'PlanCreditoVenta',
        remote_side=[id_plan_credito_venta],
        backref=db.backref('refinanciaciones', lazy='dynamic'),
    )
    cuotas = db.relationship(
        'CuotaCreditoVenta',
        backref='plan',
        lazy='selectin',
        cascade='all, delete-orphan',
        order_by='CuotaCreditoVenta.numero_cuota.asc()',
    )

    def __repr__(self):
        return f'<PlanCreditoVenta {self.id_plan_credito_venta} cuenta={self.id_cuenta_cobrar}>'


class CuotaCreditoVenta(db.Model):
    __tablename__ = 'cuotas_credito_venta'
    __table_args__ = (
        db.UniqueConstraint('id_plan_credito_venta', 'numero_cuota', name='uq_cuotas_credito_venta_plan_numero'),
        db.Index('ix_cuotas_credito_venta_estado_vencimiento', 'estado', 'fecha_vencimiento'),
    )

    id_cuota_credito = db.Column(db.Integer, primary_key=True)
    id_plan_credito_venta = db.Column(
        db.Integer,
        db.ForeignKey('planes_credito_venta.id_plan_credito_venta', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    numero_cuota = db.Column(db.Integer, nullable=False)
    fecha_vencimiento = db.Column(db.Date, nullable=False, index=True)
    capital_programado = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    interes_programado = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    saldo_capital = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    monto_programado = db.Column(db.Numeric(15, 2), nullable=False)
    monto_cobrado = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    saldo_pendiente = db.Column(db.Numeric(15, 2), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='pendiente', index=True)
    dias_vencido = db.Column(db.Integer, nullable=False, default=0)
    fecha_ultimo_pago = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    aplicaciones = db.relationship(
        'PagoCuentaCobrarAplicacion',
        backref='cuota',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f'<CuotaCreditoVenta {self.id_cuota_credito} plan={self.id_plan_credito_venta} cuota={self.numero_cuota}>'


class PagoCuentaCobrarAplicacion(db.Model):
    __tablename__ = 'pagos_cuentas_cobrar_aplicaciones'
    __table_args__ = (
        db.Index('ix_pagos_cuentas_cobrar_aplicaciones_pago_cuota', 'id_pago_cuenta', 'id_cuota_credito'),
    )

    id_aplicacion = db.Column(db.Integer, primary_key=True)
    id_pago_cuenta = db.Column(
        db.Integer,
        db.ForeignKey('pagos_cuentas_cobrar.id_pago_cuenta', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    id_cuota_credito = db.Column(
        db.Integer,
        db.ForeignKey('cuotas_credito_venta.id_cuota_credito', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    monto_aplicado = db.Column(db.Numeric(15, 2), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    pago = db.relationship(
        'PagoCuentaCobrar',
        backref=db.backref('aplicaciones_cuotas', lazy='dynamic', cascade='all, delete-orphan'),
    )

    def __repr__(self):
        return f'<PagoCuentaCobrarAplicacion pago={self.id_pago_cuenta} cuota={self.id_cuota_credito}>'


__all__ = [
    'CuentaPorCobrar',
    'PagoCuentaCobrar',
    'PlanCreditoVenta',
    'CuotaCreditoVenta',
    'PagoCuentaCobrarAplicacion',
]
