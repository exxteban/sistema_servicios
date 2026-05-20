"""
Modelos para el sistema de WhatsApp
- Conversaciones con contexto y sesiones
- Mensajes (historial completo)
- Configuracion FAQ editable
- Estado online/offline de asesores
- Asignacion exclusiva de conversaciones
- Codigos de verificacion
"""
from datetime import datetime
from app import db


class WhatsAppConversacion(db.Model):
    """Sesion de conversacion WhatsApp con contexto"""
    __tablename__ = 'whatsapp_conversaciones'
    __table_args__ = (
        db.Index('ix_whatsapp_conversaciones_activa_modo_ultima_actividad', 'activa', 'modo', 'ultima_actividad'),
    )

    id = db.Column(db.Integer, primary_key=True)
    telefono = db.Column(db.String(20), nullable=False, index=True)
    nombre_contacto = db.Column(db.String(200))

    # Modo: bot, derivacion, asesor
    modo = db.Column(db.String(20), default='bot', nullable=False)

    # Contexto de la conversacion (JSON serializado)
    # Ej: {"reparacion_seleccionada": 102, "verificado": true, "paso": "consulta_estado"}
    contexto = db.Column(db.Text)

    # Sesion
    activa = db.Column(db.Boolean, default=True, index=True)
    inicio_sesion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ultima_actividad = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fin_sesion = db.Column(db.DateTime)

    # Rate limiting
    mensajes_hora = db.Column(db.Integer, default=0)
    ultimo_reset_rate = db.Column(db.DateTime, default=datetime.utcnow)

    # Bloqueo por intentos fallidos de codigo
    intentos_codigo_fallidos = db.Column(db.Integer, default=0)
    bloqueado_hasta = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    mensajes = db.relationship(
        'WhatsAppMensaje', backref='conversacion', lazy='dynamic',
        order_by='WhatsAppMensaje.created_at', cascade='all, delete-orphan'
    )
    eventos = db.relationship(
        'WhatsAppConversacionEvento', backref='conversacion', lazy='dynamic',
        order_by='WhatsAppConversacionEvento.created_at', cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<WhatsAppConversacion {self.id} - {self.telefono} ({self.modo})>'


class WhatsAppMensaje(db.Model):
    """Mensaje individual de WhatsApp (entrante o saliente)"""
    __tablename__ = 'whatsapp_mensajes'
    __table_args__ = (
        db.Index('ix_whatsapp_mensajes_conversacion_direccion_created_at', 'id_conversacion', 'direccion', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    id_conversacion = db.Column(db.Integer, db.ForeignKey('whatsapp_conversaciones.id'), nullable=False, index=True)

    # Direccion: entrante (cliente->sistema) o saliente (sistema->cliente)
    direccion = db.Column(db.String(10), nullable=False)  # 'entrante' o 'saliente'

    # Quien envia/recibe
    remitente = db.Column(db.String(20), nullable=False)  # 'cliente', 'bot', 'asesor'
    id_asesor = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))

    # Contenido
    tipo_mensaje = db.Column(db.String(20), default='text')  # text, image, audio, document, interactive, template
    contenido = db.Column(db.Text, nullable=False)
    media_url = db.Column(db.String(500))

    # WhatsApp message ID (para tracking)
    wa_message_id = db.Column(db.String(100), index=True)
    wa_status = db.Column(db.String(20))  # sent, delivered, read, failed

    # Tool calls (si el bot uso function calling)
    tool_call = db.Column(db.Text)  # JSON: {"name": "consultar_estado", "args": {...}, "result": {...}}

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relacion con asesor
    asesor = db.relationship('Usuario', foreign_keys=[id_asesor])

    def __repr__(self):
        return f'<WhatsAppMensaje {self.id} - {self.direccion} ({self.remitente})>'


class WhatsAppConversacionEvento(db.Model):
    """Evento operativo/auditable de una conversación de WhatsApp."""
    __tablename__ = 'whatsapp_conversacion_eventos'
    __table_args__ = (
        db.Index('ix_whatsapp_conversacion_eventos_conv_created_at', 'id_conversacion', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    id_conversacion = db.Column(db.Integer, db.ForeignKey('whatsapp_conversaciones.id'), nullable=False, index=True)
    tipo = db.Column(db.String(40), nullable=False, index=True)
    actor = db.Column(db.String(20), nullable=False, default='sistema')
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))
    detalle = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    usuario = db.relationship('Usuario', foreign_keys=[id_usuario])

    def __repr__(self):
        return f'<WhatsAppConversacionEvento {self.id} conv={self.id_conversacion} tipo={self.tipo}>'


class WhatsAppConfiguracion(db.Model):
    """Configuracion editable del bot: FAQ, horarios, mensajes, etc."""
    __tablename__ = 'whatsapp_configuracion'

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(50), unique=True, nullable=False, index=True)
    valor = db.Column(db.Text, nullable=False)
    descripcion = db.Column(db.String(200))
    categoria = db.Column(db.String(30), default='general')  # general, faq, mensaje, limite
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<WhatsAppConfiguracion {self.clave}>'


class WhatsAppEstadoAsesor(db.Model):
    """Estado online/offline de cada asesor para WhatsApp"""
    __tablename__ = 'whatsapp_estado_asesor'

    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), primary_key=True)
    online = db.Column(db.Boolean, default=False, nullable=False)
    ultimo_ping = db.Column(db.DateTime)
    conversaciones_activas = db.Column(db.Integer, default=0, nullable=False)
    max_conversaciones = db.Column(db.Integer, default=5, nullable=False)
    conectado_desde = db.Column(db.DateTime)
    ultima_asignacion = db.Column(db.DateTime)  # Para algoritmo Round Robin

    usuario = db.relationship('Usuario', backref=db.backref('estado_whatsapp', uselist=False))

    def __repr__(self):
        return f'<WhatsAppEstadoAsesor {self.id_usuario} online={self.online}>'


class WhatsAppAsignacionConversacion(db.Model):
    """Asignacion exclusiva de conversacion a un asesor"""
    __tablename__ = 'whatsapp_asignacion_conversacion'

    id = db.Column(db.Integer, primary_key=True)
    id_conversacion = db.Column(db.Integer, db.ForeignKey('whatsapp_conversaciones.id'), unique=True, nullable=False)
    id_asesor = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False, index=True)

    # Control
    asignado_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    aceptado_at = db.Column(db.DateTime)
    cerrado_at = db.Column(db.DateTime)
    estado = db.Column(db.String(20), default='pendiente', nullable=False)  # pendiente, activa, cerrada, devuelta

    # Tracking para políticas de timeout
    ultima_respuesta_asesor_at = db.Column(db.DateTime)  # Última vez que el asesor escribió (detecta Política B)
    motivo_devolucion = db.Column(db.String(30))  # timeout_no_aceptado | timeout_sin_respuesta | manual | asesor_offline

    conversacion = db.relationship('WhatsAppConversacion', backref=db.backref('asignacion', uselist=False))
    asesor = db.relationship('Usuario', backref=db.backref('asignaciones_whatsapp', lazy='dynamic'))

    def __repr__(self):
        return f'<WhatsAppAsignacion {self.id} conv={self.id_conversacion} asesor={self.id_asesor} ({self.estado})>'


class WhatsAppCodigoVerificacion(db.Model):
    """Codigos de verificacion de 6 digitos para acceso a datos sensibles"""
    __tablename__ = 'whatsapp_codigos_verificacion'

    id = db.Column(db.Integer, primary_key=True)
    telefono = db.Column(db.String(20), nullable=False, index=True)
    id_reparacion = db.Column(db.Integer, db.ForeignKey('reparaciones.id_reparacion'), nullable=False)
    codigo_hash = db.Column(db.String(64), nullable=False)  # SHA-256
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expira_at = db.Column(db.DateTime, nullable=False)
    usado = db.Column(db.Boolean, default=False, nullable=False)
    intentos_fallidos = db.Column(db.Integer, default=0, nullable=False)

    reparacion = db.relationship('Reparacion')

    def __repr__(self):
        return f'<WhatsAppCodigo {self.id} tel={self.telefono} rep={self.id_reparacion}>'
