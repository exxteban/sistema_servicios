"""
Modelo de Configuración del Sistema
"""
from app import db


class Configuracion(db.Model):
    __tablename__ = 'configuracion'
    
    clave = db.Column(db.String(50), primary_key=True)
    valor = db.Column(db.Text, nullable=False)
    descripcion = db.Column(db.Text)
    fecha_modificacion = db.Column(db.DateTime)
    
    @classmethod
    def obtener(cls, clave, default=None):
        """Obtiene un valor de configuración"""
        config = db.session.get(cls, clave)
        return config.valor if config else default
    
    @classmethod
    def establecer(cls, clave, valor, descripcion=None):
        """Establece un valor de configuración"""
        from datetime import datetime
        config = db.session.get(cls, clave)
        if config:
            config.valor = valor
            config.fecha_modificacion = datetime.utcnow()
        else:
            config = cls(clave=clave, valor=valor, descripcion=descripcion)
            db.session.add(config)
        db.session.commit()
        return config
    
    @classmethod
    def obtener_bool(cls, clave, default=False):
        """Obtiene un valor booleano de configuración"""
        valor = cls.obtener(clave)
        return cls.parse_bool(valor, default=default)

    @staticmethod
    def parse_bool(valor, default=False):
        """Normaliza distintos tipos de entrada a bool de forma segura."""
        if valor is None:
            return default
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, (int, float)):
            return valor != 0
        try:
            texto = str(valor).strip().lower()
        except Exception:
            return default
        if texto in ('1', 'true', 'yes', 'si', 'sí', 'on', 'y', 't'):
            return True
        if texto in ('0', 'false', 'no', 'off', 'n', 'f', ''):
            return False
        return default

    @classmethod
    def establecer_bool(cls, clave, valor, descripcion=None):
        """Establece un valor booleano persistido como '1' o '0'."""
        normalizado = cls.parse_bool(valor, default=False)
        return cls.establecer(clave, '1' if normalizado else '0', descripcion=descripcion)
    
    @classmethod
    def obtener_int(cls, clave, default=0):
        """Obtiene un valor entero de configuración"""
        valor = cls.obtener(clave)
        try:
            return int(valor)
        except (TypeError, ValueError):
            return default
    
    def __repr__(self):
        return f'<Configuracion {self.clave}={self.valor}>'
