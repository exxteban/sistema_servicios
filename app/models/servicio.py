from datetime import datetime
from decimal import Decimal

from app import db


CLIENTE_SERVICIO_ESTADOS = (
    'solicitado',
    'presupuestado',
    'agendado',
    'en_proceso',
    'completado',
    'cancelado',
    'migrado',
)


class Servicio(db.Model):
    __tablename__ = 'servicios'
    __table_args__ = (
        db.Index('ix_servicios_activo', 'activo'),
        db.Index('ix_servicios_publicado', 'publicado_tienda', 'activo'),
    )

    id_servicio = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), nullable=True, index=True)
    nombre = db.Column(db.String(200), nullable=False, index=True)
    categoria = db.Column(db.String(100), nullable=True)
    descripcion = db.Column(db.Text)
    costo = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    duracion_minutos = db.Column(db.Integer, nullable=False, default=30)
    porcentaje_iva = db.Column(db.Integer, nullable=False, default=10)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    turno_rapido_tipo = db.Column(db.String(30), nullable=True, index=True)
    publicado_tienda = db.Column(db.Boolean, default=False, nullable=False)
    descripcion_tienda = db.Column(db.Text, nullable=True)
    orden_tienda = db.Column(db.Integer, default=0, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    id_usuario_modificacion = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))

    opciones = db.relationship(
        'ServicioPrecioOpcion',
        backref='servicio',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f'<Servicio {self.codigo or self.id_servicio} - {self.nombre}>'


class ServicioPrecioOpcion(db.Model):
    __tablename__ = 'servicio_precios_opciones'
    __table_args__ = (
        db.Index('ix_servicio_precios_opciones_servicio_activo', 'id_servicio', 'activo'),
    )

    id_opcion_precio = db.Column(db.Integer, primary_key=True)
    id_servicio = db.Column(
        db.Integer,
        db.ForeignKey('servicios.id_servicio', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    etiqueta = db.Column(db.String(100), nullable=False)
    costo = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ServicioPrecioOpcion {self.id_servicio} {self.etiqueta} {self.precio}>'


class ClienteServicio(db.Model):
    __tablename__ = 'cliente_servicios'
    __table_args__ = (
        db.Index('ix_cliente_servicios_cliente_estado', 'id_cliente', 'estado'),
        db.Index('ix_cliente_servicios_servicio_estado', 'id_servicio', 'estado'),
        db.Index('ix_cliente_servicios_fecha', 'fecha_solicitud'),
    )

    id_cliente_servicio = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    id_servicio = db.Column(
        db.Integer,
        db.ForeignKey('servicios.id_servicio', ondelete='RESTRICT'),
        nullable=False,
        index=True,
    )
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    costo_pactado = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    precio_pactado = db.Column(db.Numeric(10, 2), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='solicitado', index=True)
    fecha_solicitud = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    fecha_programada = db.Column(db.DateTime)
    fecha_cierre = db.Column(db.DateTime)
    observaciones = db.Column(db.Text)
    id_venta = db.Column(db.Integer, db.ForeignKey('ventas.id_venta'), index=True)
    id_usuario_registro = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))

    cliente = db.relationship(
        'Cliente',
        backref=db.backref(
            'servicios_contratados',
            lazy='dynamic',
            cascade='all, delete-orphan',
            order_by='ClienteServicio.fecha_solicitud.desc()',
        ),
    )
    servicio = db.relationship(
        'Servicio',
        backref=db.backref('asignaciones_cliente', lazy='dynamic'),
    )
    usuario_registro = db.relationship('Usuario', foreign_keys=[id_usuario_registro])
    venta = db.relationship('Venta', foreign_keys=[id_venta])

    @property
    def subtotal(self):
        cantidad = max(int(self.cantidad or 0), 0)
        return Decimal(self.precio_pactado or 0) * cantidad

    @property
    def estado_display(self):
        labels = {
            'solicitado': 'Solicitado',
            'presupuestado': 'Presupuestado',
            'agendado': 'Agendado',
            'en_proceso': 'En proceso',
            'completado': 'Completado',
            'cancelado': 'Cancelado',
            'migrado': 'Migrado',
        }
        return labels.get(self.estado, (self.estado or '').replace('_', ' ').title())

    def __repr__(self):
        return f'<ClienteServicio cliente={self.id_cliente} servicio={self.id_servicio}>'
