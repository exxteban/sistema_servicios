"""
Modelos del asistente IA interno del backoffice.
"""
from datetime import datetime

from app import db


class AsistenteIABackofficeAudit(db.Model):
    __tablename__ = 'asistente_ia_backoffice_audit'

    id_audit = db.Column(db.Integer, primary_key=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True, index=True)
    username = db.Column(db.String(80), nullable=True, index=True)
    fecha_hora = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    pregunta = db.Column(db.Text, nullable=False, default='')
    respuesta = db.Column(db.Text, nullable=False, default='')
    tools_usadas = db.Column(db.Text, nullable=False, default='[]')
    argumentos_normalizados = db.Column(db.Text, nullable=False, default='{}')
    resultado_resumido = db.Column(db.Text, nullable=False, default='')
    tokens_prompt = db.Column(db.Integer, nullable=False, default=0)
    tokens_completion = db.Column(db.Integer, nullable=False, default=0)
    tokens_total = db.Column(db.Integer, nullable=False, default=0)
    modelo = db.Column(db.String(120), nullable=False, default='')
    provider = db.Column(db.String(40), nullable=False, default='')
    estado = db.Column(db.String(40), nullable=False, default='ok', index=True)
    ip = db.Column(db.String(80), nullable=False, default='')
    user_agent = db.Column(db.String(255), nullable=False, default='')

    usuario = db.relationship('Usuario', backref=db.backref('asistente_ia_audits', lazy='dynamic'))

    def __repr__(self):
        return f'<AsistenteIABackofficeAudit {self.id_audit}:{self.estado}>'
