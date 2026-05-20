"""
Modelo de Permiso
"""
from app import db


class Permiso(db.Model):
    __tablename__ = 'permisos'
    
    id_permiso = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    modulo = db.Column(db.String(50), nullable=False, index=True)
    requiere_autorizacion = db.Column(db.Boolean, default=False)
    activo = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<Permiso {self.codigo}>'
    
    @staticmethod
    def requiere_autorizacion_admin(codigo_permiso):
        """Verifica si un permiso requiere autorización de administrador"""
        permiso = Permiso.query.filter_by(codigo=codigo_permiso, activo=True).first()
        return permiso.requiere_autorizacion if permiso else False
