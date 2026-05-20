"""
Modelo CRM - Contacto
Representa un contacto unificado (cliente de WhatsApp).
Se auto-crea al primer mensaje entrante y se enriquece con datos del sistema.
"""
from datetime import datetime
from app import db


class CrmContacto(db.Model):
    """Contacto CRM: una persona que interactuó por WhatsApp."""
    __tablename__ = 'crm_contactos'

    id = db.Column(db.Integer, primary_key=True)
    telefono = db.Column(db.String(20), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(200))

    # Vinculo con cliente del sistema principal (opcional)
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=True, index=True)

    # Metadatos
    primer_contacto = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ultimo_contacto = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    total_conversaciones = db.Column(db.Integer, default=0, nullable=False)

    # Estado
    bloqueado = db.Column(db.Boolean, default=False, nullable=False)
    notas_generales = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    cliente = db.relationship('Cliente', backref=db.backref('crm_contacto', uselist=False))
    etiquetas = db.relationship(
        'CrmEtiqueta',
        secondary='crm_contacto_etiquetas',
        backref=db.backref('contactos', lazy='dynamic'),
        lazy='dynamic'
    )
    notas = db.relationship(
        'CrmNotaInterna', backref='contacto', lazy='dynamic',
        order_by='CrmNotaInterna.created_at.desc()', cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<CrmContacto {self.id} - {self.telefono} ({self.nombre})>'

    def to_dict(self):
        return {
            'id': self.id,
            'telefono': self.telefono,
            'nombre': self.nombre or '',
            'id_cliente': self.id_cliente,
            'primer_contacto': self.primer_contacto.isoformat() if self.primer_contacto else None,
            'ultimo_contacto': self.ultimo_contacto.isoformat() if self.ultimo_contacto else None,
            'total_conversaciones': self.total_conversaciones,
            'bloqueado': self.bloqueado,
            'notas_generales': self.notas_generales or '',
            'etiquetas': [e.to_dict() for e in self.etiquetas.all()],
        }


# Tabla de asociación contacto <-> etiqueta
crm_contacto_etiquetas = db.Table(
    'crm_contacto_etiquetas',
    db.Column('id_contacto', db.Integer, db.ForeignKey('crm_contactos.id'), primary_key=True),
    db.Column('id_etiqueta', db.Integer, db.ForeignKey('crm_etiquetas.id'), primary_key=True),
)
