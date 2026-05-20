"""
Modelo de Usuario
"""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager

_CACHE_MISS = object()


# Tabla de asociación para permisos adicionales por usuario
usuario_permisos_adicionales = db.Table('usuario_permisos_adicionales',
    db.Column('id_usuario_permiso', db.Integer, primary_key=True, autoincrement=True),
    db.Column('id_usuario', db.Integer, db.ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False),
    db.Column('id_permiso', db.Integer, db.ForeignKey('permisos.id_permiso', ondelete='CASCADE'), nullable=False),
    db.Column('concedido_por', db.Integer, db.ForeignKey('usuarios.id_usuario')),
    db.Column('fecha_concesion', db.DateTime, default=datetime.utcnow),
    db.Column('fecha_expiracion', db.DateTime),
    db.UniqueConstraint('id_usuario', 'id_permiso', name='uq_usuario_permiso')
)


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    
    id_usuario = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=True, index=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre_completo = db.Column(db.String(100), nullable=False)
    id_rol = db.Column(db.Integer, db.ForeignKey('roles.id_rol'), nullable=False, default=3)
    activo = db.Column(db.Boolean, default=True)
    dashboard_range_preference = db.Column(db.String(20), default='hoy')  # Preferencia de rango de fecha del dashboard
    ultimo_acceso = db.Column(db.DateTime)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones (rol se define en Rol con backref)
    sesiones_caja = db.relationship('SesionCaja', backref='usuario', lazy='dynamic',
                                     foreign_keys='SesionCaja.id_usuario')
    permisos_adicionales = db.relationship('Permiso', secondary=usuario_permisos_adicionales,
                                          primaryjoin='Usuario.id_usuario==usuario_permisos_adicionales.c.id_usuario',
                                          secondaryjoin='Permiso.id_permiso==usuario_permisos_adicionales.c.id_permiso',
                                          backref='usuarios_con_permiso_adicional', lazy='dynamic')
    cliente = db.relationship('Cliente', foreign_keys=[id_cliente])
    
    def get_id(self):
        return str(self.id_usuario)

    @property
    def cliente_id(self):
        return self.id_cliente

    @cliente_id.setter
    def cliente_id(self, value):
        self.id_cliente = value
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def _get_cached_attr(self, name):
        return getattr(self, name, _CACHE_MISS)

    def _set_cached_attr(self, name, value):
        setattr(self, name, value)
        return value

    def _get_rol_nombre_normalizado(self):
        cached = self._get_cached_attr('_rol_nombre_normalizado_cache')
        if cached is not _CACHE_MISS:
            return cached
        rol = getattr(self, 'rol', None)
        nombre = ((rol.nombre if rol and rol.nombre else '') or '').strip().lower()
        return self._set_cached_attr('_rol_nombre_normalizado_cache', nombre)

    def _get_modo_demo_cached(self):
        cached = self._get_cached_attr('_modo_demo_cache')
        if cached is not _CACHE_MISS:
            return cached
        raw = (self.get_preferencia('modo_demo', '0') or '').strip().lower()
        return self._set_cached_attr('_modo_demo_cache', raw in {'1', 'true', 'yes', 'si', 'sí', 'on'})

    def _get_cached_permission_codes(self):
        cached = self._get_cached_attr('_permission_codes_cache')
        if cached is not _CACHE_MISS:
            return cached

        from app.models.permiso import Permiso
        from app.models.rol import rol_permisos

        if not self.activo:
            return self._set_cached_attr('_permission_codes_cache', frozenset())

        if self._get_modo_demo_cached():
            codigos = {
                codigo
                for (codigo,) in db.session.query(Permiso.codigo)
                .filter(Permiso.activo.is_(True))
                .all()
                if codigo and (
                    codigo.startswith('ver_')
                    or codigo in self._demo_permisos_permitidos()
                )
            }
            codigos.update(
                codigo
                for (codigo,) in db.session.query(Permiso.codigo)
                .join(
                    usuario_permisos_adicionales,
                    Permiso.id_permiso == usuario_permisos_adicionales.c.id_permiso,
                )
                .filter(
                    usuario_permisos_adicionales.c.id_usuario == self.id_usuario,
                    Permiso.activo.is_(True),
                )
                .all()
                if codigo
            )
            return self._set_cached_attr('_permission_codes_cache', frozenset(codigos))

        if self.es_admin():
            codigos = {
                codigo
                for (codigo,) in db.session.query(Permiso.codigo)
                .filter(Permiso.activo.is_(True))
                .all()
                if codigo
            }
            return self._set_cached_attr('_permission_codes_cache', frozenset(codigos))

        codigos = {
            codigo
            for (codigo,) in db.session.query(Permiso.codigo)
            .join(rol_permisos, Permiso.id_permiso == rol_permisos.c.id_permiso)
            .filter(
                rol_permisos.c.id_rol == self.id_rol,
                Permiso.activo.is_(True),
            )
            .all()
            if codigo
        }
        codigos.update(
            codigo
            for (codigo,) in db.session.query(Permiso.codigo)
            .join(
                usuario_permisos_adicionales,
                Permiso.id_permiso == usuario_permisos_adicionales.c.id_permiso,
            )
            .filter(
                usuario_permisos_adicionales.c.id_usuario == self.id_usuario,
                Permiso.activo.is_(True),
            )
            .all()
            if codigo
        )
        return self._set_cached_attr('_permission_codes_cache', frozenset(codigos))
    
    def es_admin(self):
        """Verifica si el usuario es administrador"""
        cached = self._get_cached_attr('_es_admin_cache')
        if cached is not _CACHE_MISS:
            return cached
        if self.id_rol == 1:
            return self._set_cached_attr('_es_admin_cache', True)
        resultado = self._get_rol_nombre_normalizado() in ['administrador', 'admin', 'root', 'superusuario']
        return self._set_cached_attr('_es_admin_cache', resultado)
    
    def es_supervisor(self):
        """Verifica si el usuario es supervisor o administrador"""
        if self.es_admin() or self.id_rol == 2:
            return True
        if not self.rol or not self.rol.nombre:
            return False
        return self.rol.nombre.strip().lower() == 'supervisor'

    def get_preferencia(self, clave, default=None):
        pref = self.preferencias.filter_by(clave=clave).first()
        if not pref:
            return default
        return pref.valor

    def set_preferencia(self, clave, valor):
        pref = self.preferencias.filter_by(clave=clave).first()
        if valor is None:
            if pref:
                db.session.delete(pref)
            return
        val = str(valor)
        if pref:
            pref.valor = val
            return
        db.session.add(PreferenciaUsuario(id_usuario=self.id_usuario, clave=clave, valor=val))

    @property
    def modo_demo(self):
        return self._get_modo_demo_cached()

    @staticmethod
    def _demo_permisos_permitidos():
        return {
            'crear_venta',
            'aplicar_descuento',
            'venta_credito',
            'crear_producto',
            'crear_proveedor',
            'crear_reparacion',
            'abrir_caja',
            'cerrar_caja',
            'cobrar_reparacion',
            'vincular_venta_reparacion',
        }
    
    def tiene_permiso(self, codigo_permiso):
        """
        Verifica si el usuario tiene un permiso específico.
        Considera permisos del rol + permisos adicionales.
        En modo demo: permite ver_*, permisos de la lista whitelist,
        y permisos adicionales asignados explícitamente al usuario.
        """
        if not self.activo:
            return False

        codigo_permiso = (codigo_permiso or '').strip()
        if not codigo_permiso:
            return False
        cached_checks = self._get_cached_attr('_permission_check_cache')
        if cached_checks is _CACHE_MISS:
            cached_checks = {}
            self._set_cached_attr('_permission_check_cache', cached_checks)
        if codigo_permiso in cached_checks:
            return cached_checks[codigo_permiso]
        permitido = codigo_permiso in self._get_cached_permission_codes()
        cached_checks[codigo_permiso] = permitido
        return permitido

    def puede_autorizar(self, codigo_permiso):
        """
        Verifica si este usuario puede autorizar un permiso a otro usuario.
        Solo administradores pueden autorizar.
        """
        return self.es_admin() and self.tiene_permiso(codigo_permiso)
    
    def get_permisos(self):
        """Retorna lista de códigos de permisos que tiene el usuario"""
        return sorted(self._get_cached_permission_codes())
    
    def __repr__(self):
        return f'<Usuario {self.username}>'


class PreferenciaUsuario(db.Model):
    __tablename__ = 'preferencias_usuario'

    id_preferencia = db.Column(db.Integer, primary_key=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False, index=True)
    clave = db.Column(db.String(50), nullable=False)
    valor = db.Column(db.Text, nullable=False)

    usuario = db.relationship('Usuario', backref=db.backref('preferencias', lazy='dynamic', cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('id_usuario', 'clave', name='uq_usuario_clave_preferencia'),
    )

    def __repr__(self):
        return f'<PreferenciaUsuario {self.id_usuario}:{self.clave}>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))
