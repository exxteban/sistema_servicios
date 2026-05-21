from datetime import datetime

from app import db


class Servicio(db.Model):
    __tablename__ = 'servicios'
    __table_args__ = (
        db.UniqueConstraint('id_cliente', 'codigo', name='uq_servicios_cliente_codigo'),
        db.Index('ix_servicios_cliente_activo', 'id_cliente', 'activo'),
        db.Index('ix_servicios_cliente_publicado', 'id_cliente', 'publicado_tienda', 'activo'),
    )

    id_servicio = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=False, index=True)
    codigo = db.Column(db.String(50), nullable=True)
    nombre = db.Column(db.String(200), nullable=False, index=True)
    categoria = db.Column(db.String(100), nullable=True)
    descripcion = db.Column(db.Text)
    costo = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    duracion_minutos = db.Column(db.Integer, nullable=False, default=30)
    porcentaje_iva = db.Column(db.Integer, nullable=False, default=10)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    publicado_tienda = db.Column(db.Boolean, default=False, nullable=False)
    descripcion_tienda = db.Column(db.Text, nullable=True)
    orden_tienda = db.Column(db.Integer, default=0, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    id_usuario_modificacion = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))

    cliente = db.relationship('Cliente', backref='servicios', lazy='select')
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
    id_servicio = db.Column(db.Integer, db.ForeignKey('servicios.id_servicio', ondelete='CASCADE'), nullable=False, index=True)
    etiqueta = db.Column(db.String(100), nullable=False)
    costo = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ServicioPrecioOpcion {self.id_servicio} {self.etiqueta} {self.precio}>'
