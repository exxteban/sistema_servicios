"""
Modelo de Rol
"""
from datetime import datetime
from app import db


# Tabla de asociación para permisos de roles
rol_permisos = db.Table('rol_permisos',
    db.Column('id_rol_permiso', db.Integer, primary_key=True, autoincrement=True),
    db.Column('id_rol', db.Integer, db.ForeignKey('roles.id_rol', ondelete='CASCADE'), nullable=False),
    db.Column('id_permiso', db.Integer, db.ForeignKey('permisos.id_permiso', ondelete='CASCADE'), nullable=False),
    db.UniqueConstraint('id_rol', 'id_permiso', name='uq_rol_permiso')
)


class Rol(db.Model):
    __tablename__ = 'roles'
    
    id_rol = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    descripcion = db.Column(db.Text)
    nivel_jerarquia = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    usuarios = db.relationship('Usuario', backref='rol', lazy='dynamic')
    permisos = db.relationship('Permiso', secondary=rol_permisos, backref='roles', lazy='dynamic')
    
    def __repr__(self):
        return f'<Rol {self.nombre}>'
    
    def tiene_permiso(self, codigo_permiso):
        """Verifica si este rol tiene un permiso específico"""
        from app.models.permiso import Permiso
        permiso = Permiso.query.filter_by(codigo=codigo_permiso, activo=True).first()
        if not permiso:
            return False
        return permiso in self.permisos.all()
