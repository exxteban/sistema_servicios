"""Historial del asistente IA de configuracion (servidor: la cookie de sesion no alcanza)."""
from datetime import datetime

from app import db


class GastronomiaAsistenteMensaje(db.Model):
    __tablename__ = 'gastronomia_asistente_mensajes'

    id_mensaje = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False, index=True)
    rol = db.Column(db.String(20), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    contexto_json = db.Column(db.Text, nullable=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_gastro_asistente_cliente_usuario', 'cliente_id', 'usuario_id', 'id_mensaje'),
    )


class GastronomiaAsistentePropuesta(db.Model):
    """Cambios que la IA propuso y que solo se ejecutan si el usuario los confirma con el boton."""
    __tablename__ = 'gastronomia_asistente_propuestas'

    id_propuesta = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False, index=True)
    acciones_json = db.Column(db.Text, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='pendiente', index=True)
    resultado_json = db.Column(db.Text, nullable=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_resolucion = db.Column(db.DateTime, nullable=True)
