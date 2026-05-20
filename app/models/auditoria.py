"""
Modelo de Auditoría
"""
from datetime import datetime
import json
from app import db


def _mask_sensitive(value):
    if isinstance(value, dict):
        masked = {}
        for k, v in value.items():
            key = str(k).lower()
            if any(t in key for t in ('password', 'passwd', 'token', 'secret', 'apikey', 'api_key')):
                masked[k] = '***'
            else:
                masked[k] = _mask_sensitive(v)
        return masked
    if isinstance(value, list):
        return [_mask_sensitive(v) for v in value]
    return value


def _json_dumps(value):
    if value is None:
        return None
    try:
        return json.dumps(_mask_sensitive(value), ensure_ascii=False, default=str)
    except Exception:
        return None


class Auditoria(db.Model):
    __tablename__ = 'auditoria'
    
    id_auditoria = db.Column(db.Integer, primary_key=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    accion = db.Column(db.String(50), nullable=False, index=True)
    modulo = db.Column(db.String(50), nullable=False, index=True)
    descripcion = db.Column(db.Text, nullable=False)
    referencia_tipo = db.Column(db.String(30), index=True)
    referencia_id = db.Column(db.Integer)
    datos_anteriores = db.Column(db.Text)  # JSON
    datos_nuevos = db.Column(db.Text)  # JSON
    id_autorizacion = db.Column(db.Integer, db.ForeignKey('autorizaciones.id_autorizacion'))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    fecha_accion = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relaciones
    usuario = db.relationship('Usuario', backref='acciones_auditoria')
    autorizacion = db.relationship('Autorizacion', backref='registros_auditoria')
    
    def __repr__(self):
        return f'<Auditoria {self.id_auditoria} - {self.accion}>'
    
    @staticmethod
    def registrar(id_usuario, accion, modulo, descripcion, 
                 referencia_tipo=None, referencia_id=None,
                 datos_anteriores=None, datos_nuevos=None,
                 id_autorizacion=None, ip_address=None, user_agent=None,
                 commit=True):
        """
        Registra una acción en la auditoría
        
        Args:
            id_usuario: ID del usuario que realizó la acción
            accion: Código de la acción (ej: 'anular_venta')
            modulo: Módulo del sistema (ej: 'ventas')
            descripcion: Descripción legible de la acción
            referencia_tipo: Tipo de entidad afectada (ej: 'venta')
            referencia_id: ID de la entidad afectada
            datos_anteriores: Dict con datos antes del cambio
            datos_nuevos: Dict con datos después del cambio
            id_autorizacion: ID de la autorización si aplica
            ip_address: IP del usuario
            user_agent: User agent del navegador
        """
        auditoria = Auditoria(
            id_usuario=id_usuario,
            accion=accion,
            modulo=modulo,
            descripcion=descripcion,
            referencia_tipo=referencia_tipo,
            referencia_id=referencia_id,
            datos_anteriores=_json_dumps(datos_anteriores),
            datos_nuevos=_json_dumps(datos_nuevos),
            id_autorizacion=id_autorizacion,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        db.session.add(auditoria)
        if commit:
            db.session.commit()
        
        return auditoria
    
    def get_datos_anteriores(self):
        """Retorna los datos anteriores como dict"""
        return json.loads(self.datos_anteriores) if self.datos_anteriores else None
    
    def get_datos_nuevos(self):
        """Retorna los datos nuevos como dict"""
        return json.loads(self.datos_nuevos) if self.datos_nuevos else None
