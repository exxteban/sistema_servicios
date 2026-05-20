"""
Modelo CRM - Etiqueta
Etiquetas para clasificar conversaciones y contactos.
"""
from datetime import datetime
from app import db


class CrmEtiqueta(db.Model):
    """Etiqueta para clasificar contactos/conversaciones."""
    __tablename__ = 'crm_etiquetas'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7), default='#6B7280')  # hex color
    descripcion = db.Column(db.String(200))
    activa = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<CrmEtiqueta {self.id} - {self.nombre}>'

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'color': self.color,
            'descripcion': self.descripcion or '',
            'activa': self.activa,
        }
