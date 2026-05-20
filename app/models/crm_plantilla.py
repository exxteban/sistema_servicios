"""
Modelo CRM - Plantilla de Respuesta Rápida
Plantillas configurables por admin para respuestas frecuentes.
"""
from datetime import datetime
from app import db


class CrmPlantilla(db.Model):
    """Plantilla de respuesta rápida para asesores."""
    __tablename__ = 'crm_plantillas'

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    categoria = db.Column(db.String(50), default='general')
    activa = db.Column(db.Boolean, default=True, nullable=False)
    orden = db.Column(db.Integer, default=0, nullable=False)

    id_usuario_creador = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creador = db.relationship('Usuario', backref=db.backref('crm_plantillas', lazy='dynamic'))

    def __repr__(self):
        return f'<CrmPlantilla {self.id} - {self.titulo}>'

    def to_dict(self):
        return {
            'id': self.id,
            'titulo': self.titulo,
            'contenido': self.contenido,
            'categoria': self.categoria,
            'activa': self.activa,
            'orden': self.orden,
        }
