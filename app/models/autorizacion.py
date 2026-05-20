"""
Modelo de Autorización
"""
from datetime import datetime
from app import db


class Autorizacion(db.Model):
    __tablename__ = 'autorizaciones'
    
    id_autorizacion = db.Column(db.Integer, primary_key=True)
    id_usuario_solicitante = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    id_usuario_autorizador = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    id_permiso = db.Column(db.Integer, db.ForeignKey('permisos.id_permiso'), nullable=False)
    accion = db.Column(db.String(100), nullable=False)
    referencia_tipo = db.Column(db.String(30))
    referencia_id = db.Column(db.Integer)
    estado = db.Column(db.String(20), nullable=False, default='pendiente')
    fecha_solicitud = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_respuesta = db.Column(db.DateTime)
    observaciones = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    
    # Relaciones
    solicitante = db.relationship('Usuario', foreign_keys=[id_usuario_solicitante], backref='autorizaciones_solicitadas')
    autorizador = db.relationship('Usuario', foreign_keys=[id_usuario_autorizador], backref='autorizaciones_otorgadas')
    permiso = db.relationship('Permiso', backref='autorizaciones')
    
    def __repr__(self):
        return f'<Autorizacion {self.id_autorizacion} - {self.accion}>'
    
    @staticmethod
    def crear_autorizacion(id_solicitante, id_autorizador, codigo_permiso, accion, 
                          referencia_tipo=None, referencia_id=None, ip_address=None):
        """Crea una nueva autorización"""
        from app.models.permiso import Permiso
        
        permiso = Permiso.query.filter_by(codigo=codigo_permiso).first()
        if not permiso:
            raise ValueError(f"Permiso {codigo_permiso} no encontrado")
        
        autorizacion = Autorizacion(
            id_usuario_solicitante=id_solicitante,
            id_usuario_autorizador=id_autorizador,
            id_permiso=permiso.id_permiso,
            accion=accion,
            referencia_tipo=referencia_tipo,
            referencia_id=referencia_id,
            estado='aprobada',
            fecha_respuesta=datetime.utcnow(),
            ip_address=ip_address
        )
        
        db.session.add(autorizacion)
        db.session.commit()
        
        return autorizacion
