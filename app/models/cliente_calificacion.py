from datetime import datetime

from app import db


class ClienteCalificacionRegla(db.Model):
    __tablename__ = 'cliente_calificacion_reglas'

    id_regla = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    metrica = db.Column(db.String(60), nullable=False, index=True)
    operador = db.Column(db.String(10), nullable=False, default='>=')
    valor = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    periodo_dias = db.Column(db.Integer)
    accion = db.Column(db.String(30), nullable=False, default='asignar')
    estrellas = db.Column(db.Integer, nullable=False, default=3)
    prioridad = db.Column(db.Integer, nullable=False, default=100)
    reaplicar_cada_dias = db.Column(db.Integer, nullable=False, default=0)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    historial = db.relationship(
        'ClienteCalificacionHistorial',
        backref='regla',
        lazy='dynamic',
    )

    @property
    def estrellas_seguras(self):
        try:
            estrellas = int(self.estrellas or 0)
        except (TypeError, ValueError):
            estrellas = 3
        return max(1, min(5, estrellas))

    @property
    def periodo_dias_seguro(self):
        try:
            periodo = int(self.periodo_dias or 0)
        except (TypeError, ValueError):
            periodo = 0
        return max(0, periodo)

    @property
    def reaplicar_cada_dias_seguro(self):
        try:
            dias = int(self.reaplicar_cada_dias or 0)
        except (TypeError, ValueError):
            dias = 0
        return max(0, dias)

    def __repr__(self):
        return f'<ClienteCalificacionRegla {self.nombre}>'


class ClienteCalificacionHistorial(db.Model):
    __tablename__ = 'cliente_calificacion_historial'

    id_historial = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    id_regla = db.Column(
        db.Integer,
        db.ForeignKey('cliente_calificacion_reglas.id_regla', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True)
    estrellas_anteriores = db.Column(db.Integer, nullable=False)
    estrellas_nuevas = db.Column(db.Integer, nullable=False)
    motivo = db.Column(db.Text, nullable=False)
    fecha_cambio = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    cliente = db.relationship('Cliente')
    usuario = db.relationship('Usuario')

    def __repr__(self):
        return f'<ClienteCalificacionHistorial cliente={self.id_cliente}>'
