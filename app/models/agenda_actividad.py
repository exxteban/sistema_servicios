from datetime import datetime
from app import db


agenda_actividad_visible_usuarios = db.Table(
    'agenda_actividad_visible_usuarios',
    db.Column('actividad_id', db.Integer, db.ForeignKey('agenda_actividades.id', ondelete='CASCADE'), primary_key=True),
    db.Column('usuario_id', db.Integer, db.ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), primary_key=True),
)


agenda_actividad_recordatorio_usuarios = db.Table(
    'agenda_actividad_recordatorio_usuarios',
    db.Column('actividad_id', db.Integer, db.ForeignKey('agenda_actividades.id', ondelete='CASCADE'), primary_key=True),
    db.Column('usuario_id', db.Integer, db.ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), primary_key=True),
)


class AgendaActividad(db.Model):
    __tablename__ = 'agenda_actividades'
    __table_args__ = (
        db.Index('ix_agenda_actividades_usuario_id', 'usuario_id'),
        db.Index('ix_agenda_actividades_fecha_inicio', 'fecha_inicio'),
        db.Index('ix_agenda_actividades_estado', 'estado'),
        db.Index('ix_agenda_actividades_estado_fecha_inicio', 'estado', 'fecha_inicio'),
        db.Index('ix_agenda_actividades_cliente_id', 'cliente_id'),
        db.Index('ix_agenda_actividades_reparacion_id', 'reparacion_id'),
        db.Index('ix_agenda_actividades_crm_contacto_id', 'crm_contacto_id'),
        db.Index('ix_agenda_actividades_mostrar_agenda_en', 'mostrar_agenda_en'),
        db.Index('ix_agenda_actividades_recordatorio_a', 'recordatorio_a'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(30), nullable=False, default='tarea_interna')
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    fecha_inicio = db.Column(db.DateTime, nullable=False)
    fecha_fin = db.Column(db.DateTime)
    estado = db.Column(db.String(20), nullable=False, default='pendiente')
    prioridad = db.Column(db.String(20), nullable=False, default='media')
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    creado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'))
    cliente_servicio_id = db.Column(db.Integer, db.ForeignKey('cliente_servicios.id_cliente_servicio'), index=True)
    reparacion_id = db.Column(db.Integer, db.ForeignKey('reparaciones.id_reparacion'))
    venta_id = db.Column(db.Integer, db.ForeignKey('ventas.id_venta'), index=True)
    crm_contacto_id = db.Column(db.Integer, db.ForeignKey('crm_contactos.id'))
    origen_modulo = db.Column(db.String(30))
    mostrar_agenda_en = db.Column(db.String(30), nullable=False, default='solo_responsable')
    recordatorio_a = db.Column(db.String(30), nullable=False, default='solo_responsable')
    recordatorio_minutos = db.Column(db.Integer)
    es_todo_el_dia = db.Column(db.Boolean, nullable=False, default=False)
    observaciones = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario = db.relationship('Usuario', foreign_keys=[usuario_id], backref=db.backref('agenda_actividades_asignadas', lazy='dynamic'))
    creado_por = db.relationship('Usuario', foreign_keys=[creado_por_id], backref=db.backref('agenda_actividades_creadas', lazy='dynamic'))
    cliente = db.relationship('Cliente', backref=db.backref('agenda_actividades', lazy='dynamic'))
    cliente_servicio = db.relationship('ClienteServicio', backref=db.backref('agenda_actividades', lazy='dynamic'))
    reparacion = db.relationship('Reparacion', backref=db.backref('agenda_actividades', lazy='dynamic'))
    venta = db.relationship('Venta', backref=db.backref('agenda_actividades', lazy='dynamic'))
    crm_contacto = db.relationship('CrmContacto', backref=db.backref('agenda_actividades', lazy='dynamic'))
    usuarios_agenda = db.relationship(
        'Usuario',
        secondary=agenda_actividad_visible_usuarios,
        lazy='selectin',
        backref=db.backref('agenda_actividades_visibles_especificas', lazy='dynamic'),
    )
    usuarios_recordatorio = db.relationship(
        'Usuario',
        secondary=agenda_actividad_recordatorio_usuarios,
        lazy='selectin',
        backref=db.backref('agenda_actividades_recordatorio_especificas', lazy='dynamic'),
    )

    def __repr__(self):
        return f'<AgendaActividad {self.id} {self.estado}>'
