"""
Modelo CRM - Nota Interna
Notas internas por contacto/conversación, solo visibles para asesores.
"""
from datetime import datetime
from app import db


class CrmNotaInterna(db.Model):
    """Nota interna asociada a un contacto CRM."""
    __tablename__ = 'crm_notas_internas'

    id = db.Column(db.Integer, primary_key=True)
    id_contacto = db.Column(db.Integer, db.ForeignKey('crm_contactos.id'), nullable=False, index=True)
    id_conversacion = db.Column(db.Integer, db.ForeignKey('whatsapp_conversaciones.id'), nullable=True, index=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)

    contenido = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    usuario = db.relationship('Usuario', backref=db.backref('crm_notas', lazy='dynamic'))
    conversacion = db.relationship('WhatsAppConversacion', backref=db.backref('notas_crm', lazy='dynamic'))

    def __repr__(self):
        return f'<CrmNotaInterna {self.id} contacto={self.id_contacto}>'

    def to_dict(self):
        return {
            'id': self.id,
            'id_contacto': self.id_contacto,
            'id_conversacion': self.id_conversacion,
            'contenido': self.contenido,
            'autor': self.usuario.nombre_completo if self.usuario else 'Sistema',
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
