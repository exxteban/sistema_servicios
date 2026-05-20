from datetime import date, datetime
from decimal import Decimal

from app import db

IPS_APORTE_OBRERO_PORCENTAJE = Decimal('0.09')


class Empleado(db.Model):
    __tablename__ = 'control_empleados'

    id_empleado = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=True, index=True)
    nombre_completo = db.Column(db.String(120), nullable=False, index=True)
    documento = db.Column(db.String(50), nullable=True, index=True)
    telefono = db.Column(db.String(50), nullable=True)
    cargo = db.Column(db.String(80), nullable=True)
    area = db.Column(db.String(80), nullable=True)
    salario_base = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    dias_vacaciones_anuales = db.Column(db.Integer, nullable=False, default=12)
    salario_incluye_ips = db.Column(db.Boolean, nullable=False, default=False)
    tipo_pago = db.Column(db.String(20), nullable=False, default='mensual')
    fecha_ingreso = db.Column(db.Date, nullable=True)
    fecha_egreso = db.Column(db.Date, nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    notas = db.Column(db.Text, nullable=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    movimientos = db.relationship(
        'EmpleadoMovimientoSalario',
        backref='empleado',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='desc(EmpleadoMovimientoSalario.fecha_movimiento)',
    )

    pagos = db.relationship(
        'EmpleadoPago',
        backref='empleado',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='desc(EmpleadoPago.fecha_pago)',
    )

    ausencias = db.relationship(
        'EmpleadoAusencia',
        backref='empleado',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='desc(EmpleadoAusencia.fecha_desde)',
    )

    def salario_base_decimal(self) -> Decimal:
        return Decimal(self.salario_base or 0)

    def dias_vacaciones_anuales_int(self) -> int:
        return int(self.dias_vacaciones_anuales or 0)

    def ips_obrero_estimado_decimal(self) -> Decimal:
        if not self.salario_incluye_ips:
            return Decimal('0.00')
        return (self.salario_base_decimal() * IPS_APORTE_OBRERO_PORCENTAJE).quantize(Decimal('0.01'))

    def salario_neto_estimado_decimal(self) -> Decimal:
        return (self.salario_base_decimal() - self.ips_obrero_estimado_decimal()).quantize(Decimal('0.01'))

    def __repr__(self):
        return f'<Empleado {self.nombre_completo}>'


class EmpleadoMovimientoSalario(db.Model):
    __tablename__ = 'control_empleados_movimientos'

    id_movimiento = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=True, index=True)
    id_empleado = db.Column(
        db.Integer,
        db.ForeignKey('control_empleados.id_empleado', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    periodo = db.Column(db.String(7), nullable=False, index=True)
    fecha_movimiento = db.Column(db.Date, nullable=False, default=date.today, index=True)
    tipo = db.Column(db.String(20), nullable=False, index=True)
    concepto = db.Column(db.String(120), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cantidad_calculo = db.Column(db.Numeric(12, 3), nullable=True)
    unidad_calculo = db.Column(db.String(30), nullable=True)
    valor_unitario_calculo = db.Column(db.Numeric(12, 2), nullable=True)
    incide_aguinaldo = db.Column(db.Boolean, nullable=False, default=False)
    observaciones = db.Column(db.Text, nullable=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def monto_decimal(self) -> Decimal:
        return Decimal(self.monto or 0)

    def incide_aguinaldo_bool(self) -> bool:
        return bool(self.incide_aguinaldo)

    def __repr__(self):
        return f'<EmpleadoMovimientoSalario {self.id_movimiento} empleado={self.id_empleado}>'


class EmpleadoPago(db.Model):
    __tablename__ = 'control_empleados_pagos'

    id_pago = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=True, index=True)
    id_empleado = db.Column(
        db.Integer,
        db.ForeignKey('control_empleados.id_empleado', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    periodo = db.Column(db.String(7), nullable=False, index=True)
    fecha_pago = db.Column(db.Date, nullable=False, default=date.today, index=True)
    salario_base = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_extras = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_descuentos = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_pagado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    metodo_pago = db.Column(db.String(50), nullable=True)
    referencia = db.Column(db.String(120), nullable=True)
    notas = db.Column(db.Text, nullable=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def salario_base_decimal(self) -> Decimal:
        return Decimal(self.salario_base or 0)

    def total_extras_decimal(self) -> Decimal:
        return Decimal(self.total_extras or 0)

    def total_descuentos_decimal(self) -> Decimal:
        return Decimal(self.total_descuentos or 0)

    def total_pagado_decimal(self) -> Decimal:
        return Decimal(self.total_pagado or 0)

    def total_remunerativo_decimal(self) -> Decimal:
        return (self.salario_base_decimal() + self.total_extras_decimal()).quantize(Decimal('0.01'))

    def __repr__(self):
        return f'<EmpleadoPago {self.id_pago} empleado={self.id_empleado} periodo={self.periodo}>'


class EmpleadoAusencia(db.Model):
    __tablename__ = 'control_empleados_ausencias'

    id_ausencia = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=True, index=True)
    id_empleado = db.Column(
        db.Integer,
        db.ForeignKey('control_empleados.id_empleado', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    tipo = db.Column(db.String(20), nullable=False, index=True)
    estado = db.Column(db.String(20), nullable=False, default='pendiente', index=True)
    fecha_desde = db.Column(db.Date, nullable=False, index=True)
    fecha_hasta = db.Column(db.Date, nullable=False, index=True)
    motivo = db.Column(db.String(160), nullable=False)
    observaciones = db.Column(db.Text, nullable=True)
    fecha_respuesta = db.Column(db.Date, nullable=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        db.Index('ix_control_empleados_ausencias_empleado_estado_fecha', 'id_empleado', 'estado', 'fecha_desde'),
        db.Index('ix_control_empleados_ausencias_empleado_rango', 'id_empleado', 'fecha_desde', 'fecha_hasta'),
    )

    def dias_totales(self) -> int:
        if not self.fecha_desde or not self.fecha_hasta:
            return 0
        return max((self.fecha_hasta - self.fecha_desde).days + 1, 0)

    def __repr__(self):
        return f'<EmpleadoAusencia {self.id_ausencia} empleado={self.id_empleado} tipo={self.tipo}>'


class EmpleadoTipoAusencia(db.Model):
    __tablename__ = 'control_empleados_tipos_ausencia'

    id_tipo_ausencia = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=False, index=True)
    clave = db.Column(db.String(20), nullable=False, index=True)
    nombre = db.Column(db.String(80), nullable=False)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            'cliente_id',
            'clave',
            name='uq_control_empleados_tipo_ausencia_cliente_clave',
        ),
        db.Index(
            'ix_control_empleados_tipo_ausencia_cliente_nombre',
            'cliente_id',
            'nombre',
        ),
    )

    def __repr__(self):
        return (
            f'<EmpleadoTipoAusencia {self.id_tipo_ausencia} '
            f'cliente={self.cliente_id} clave={self.clave}>'
        )


class EmpleadoFeriado(db.Model):
    __tablename__ = 'control_empleados_feriados'

    id_feriado = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=True, index=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    motivo = db.Column(db.String(160), nullable=False)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'fecha', name='uq_control_empleados_feriado_cliente_fecha'),
        db.Index('ix_control_empleados_feriados_cliente_fecha', 'cliente_id', 'fecha'),
    )

    def __repr__(self):
        return f'<EmpleadoFeriado {self.id_feriado} cliente={self.cliente_id} fecha={self.fecha}>'


# Estados posibles para un día de asistencia
ESTADO_ASISTENCIA_PRESENTE = 'presente'
ESTADO_ASISTENCIA_AUSENTE = 'ausente'
ESTADO_ASISTENCIA_MEDIO_DIA = 'medio_dia'
ESTADO_ASISTENCIA_FERIADO = 'feriado'
ESTADOS_ASISTENCIA_VALIDOS = frozenset([
    ESTADO_ASISTENCIA_PRESENTE,
    ESTADO_ASISTENCIA_AUSENTE,
    ESTADO_ASISTENCIA_MEDIO_DIA,
    ESTADO_ASISTENCIA_FERIADO,
])


class EmpleadoAsistenciaDia(db.Model):
    """Registro de asistencia diaria por empleado y período.

    Permite tildar cada día de la semana (lunes a domingo) con su estado:
    presente, ausente, medio día o feriado. El sistema calcula el descuento
    automáticamente según el valor diario del sueldo base.
    """
    __tablename__ = 'control_empleados_asistencia'

    id_asistencia = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, nullable=True, index=True)
    id_empleado = db.Column(
        db.Integer,
        db.ForeignKey('control_empleados.id_empleado', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    periodo = db.Column(db.String(7), nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=False, index=True)
    # 'presente' | 'ausente' | 'medio_dia' | 'feriado'
    estado = db.Column(db.String(20), nullable=False, default=ESTADO_ASISTENCIA_PRESENTE)
    observaciones = db.Column(db.String(160), nullable=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            'id_empleado', 'fecha',
            name='uq_control_empleados_asistencia_empleado_fecha',
        ),
        db.Index(
            'ix_control_empleados_asistencia_empleado_periodo',
            'id_empleado', 'periodo',
        ),
    )

    def __repr__(self):
        return (
            f'<EmpleadoAsistenciaDia {self.id_asistencia} '
            f'empleado={self.id_empleado} fecha={self.fecha} estado={self.estado}>'
        )
