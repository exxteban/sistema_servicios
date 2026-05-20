"""
Modelos para el sistema de seguimiento público de reparaciones
"""
from datetime import datetime
from app import db


class ReparacionSeguimiento(db.Model):
    """Token de acceso público para seguimiento de reparaciones"""
    __tablename__ = 'reparacion_seguimiento'
    
    id = db.Column(db.Integer, primary_key=True)
    id_reparacion = db.Column(db.Integer, db.ForeignKey('reparaciones.id_reparacion'), nullable=False, unique=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)  # SHA-256
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)  # NULL = activo
    last_accessed_at = db.Column(db.DateTime, nullable=True)
    access_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Relación con reparación
    reparacion = db.relationship('Reparacion', backref=db.backref('seguimiento', uselist=False))
    
    @property
    def is_active(self):
        """Verifica si el token está activo (no revocado)"""
        return self.revoked_at is None
    
    def __repr__(self):
        return f'<ReparacionSeguimiento {self.id} - Reparacion {self.id_reparacion}>'


class ReparacionHistorialEstado(db.Model):
    """Timeline de cambios de estado de reparaciones"""
    __tablename__ = 'reparacion_historial_estado'
    
    id = db.Column(db.Integer, primary_key=True)
    id_reparacion = db.Column(db.Integer, db.ForeignKey('reparaciones.id_reparacion'), nullable=False, index=True)
    estado_anterior = db.Column(db.String(20), nullable=True)  # NULL en primera entrada
    estado_nuevo = db.Column(db.String(20), nullable=False)
    fecha_cambio = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    nota = db.Column(db.Text, nullable=True)  # Nota opcional del técnico
    
    # Relación con reparación
    reparacion = db.relationship('Reparacion', backref=db.backref('historial_estados', lazy='dynamic', order_by='ReparacionHistorialEstado.fecha_cambio'))
    
    def __repr__(self):
        return f'<HistorialEstado {self.id} - {self.estado_anterior} → {self.estado_nuevo}>'


class SeguimientoAcceso(db.Model):
    """Log de accesos para estadísticas del panel de seguimiento"""
    __tablename__ = 'seguimiento_accesos'
    
    id = db.Column(db.Integer, primary_key=True)
    id_seguimiento = db.Column(db.Integer, db.ForeignKey('reparacion_seguimiento.id'), nullable=False, index=True)
    accessed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv6 compatible
    user_agent = db.Column(db.String(256), nullable=True)
    
    # Relación con seguimiento
    seguimiento = db.relationship('ReparacionSeguimiento', backref=db.backref('accesos', lazy='dynamic', order_by='SeguimientoAcceso.accessed_at.desc()'))
    
    def __repr__(self):
        return f'<SeguimientoAcceso {self.id} - {self.accessed_at}>'
