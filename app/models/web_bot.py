"""
Modelos del bot web de tienda.
Cada sesión queda aislada por cliente y slug de tienda.
"""
from datetime import datetime

from app import db


class WebBotSesion(db.Model):
    __tablename__ = 'web_bot_sesiones'
    __table_args__ = (
        db.Index('ix_web_bot_sesiones_cliente_slug_estado', 'id_cliente', 'slug_tienda', 'estado'),
    )

    id_sesion = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    slug_tienda = db.Column(db.String(80), nullable=False, index=True)
    session_token = db.Column(db.String(120), nullable=False, unique=True, index=True)
    origen = db.Column(db.String(30), nullable=False, default='tienda_widget', server_default='tienda_widget')
    estado = db.Column(db.String(20), nullable=False, default='bot', server_default='bot', index=True)
    nombre_visitante = db.Column(db.String(200), nullable=True)
    telefono_visitante = db.Column(db.String(50), nullable=True)
    email_visitante = db.Column(db.String(200), nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)
    ultimo_handoff_token = db.Column(db.String(40), nullable=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_modificacion = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    ultima_actividad = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    cliente = db.relationship('Cliente', backref='web_bot_sesiones', lazy='select')
    mensajes = db.relationship(
        'WebBotMensaje',
        backref='sesion',
        lazy='dynamic',
        order_by='WebBotMensaje.created_at.asc()',
        cascade='all, delete-orphan',
    )
    handoffs = db.relationship(
        'WebBotHandoff',
        backref='sesion',
        lazy='dynamic',
        order_by='WebBotHandoff.created_at.desc()',
        cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f'<WebBotSesion {self.id_sesion} {self.slug_tienda} {self.estado}>'


class WebBotMensaje(db.Model):
    __tablename__ = 'web_bot_mensajes'
    __table_args__ = (
        db.Index('ix_web_bot_mensajes_sesion_created_at', 'id_sesion', 'created_at'),
    )

    id_mensaje = db.Column(db.Integer, primary_key=True)
    id_sesion = db.Column(
        db.Integer,
        db.ForeignKey('web_bot_sesiones.id_sesion', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    direccion = db.Column(db.String(10), nullable=False)
    remitente = db.Column(db.String(20), nullable=False)
    tipo_mensaje = db.Column(db.String(20), nullable=False, default='text', server_default='text')
    contenido = db.Column(db.Text, nullable=False)
    tool_call_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f'<WebBotMensaje {self.id_mensaje} sesion={self.id_sesion} {self.remitente}>'


class WebBotHandoff(db.Model):
    __tablename__ = 'web_bot_handoffs'
    __table_args__ = (
        db.Index('ix_web_bot_handoffs_token_estado', 'handoff_token', 'estado'),
    )

    id_handoff = db.Column(db.Integer, primary_key=True)
    id_sesion = db.Column(
        db.Integer,
        db.ForeignKey('web_bot_sesiones.id_sesion', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    handoff_token = db.Column(db.String(40), nullable=False, unique=True, index=True)
    canal_destino = db.Column(db.String(20), nullable=False, default='whatsapp', server_default='whatsapp')
    estado = db.Column(db.String(20), nullable=False, default='generado', server_default='generado')
    telefono_destino = db.Column(db.String(50), nullable=True)
    texto_prefill = db.Column(db.Text, nullable=True)
    id_whatsapp_conversacion = db.Column(
        db.Integer,
        db.ForeignKey('whatsapp_conversaciones.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    used_at = db.Column(db.DateTime, nullable=True)

    whatsapp_conversacion = db.relationship('WhatsAppConversacion', lazy='select')

    def __repr__(self):
        return f'<WebBotHandoff {self.handoff_token} {self.estado}>'
