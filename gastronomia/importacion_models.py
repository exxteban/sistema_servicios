"""Modelos para importar ventas historicas desde Excel."""
import json
from datetime import datetime

from app import db


class GastronomiaImportacion(db.Model):
    """Un lote de ventas importadas; permite deshacerlo completo."""
    __tablename__ = 'gastronomia_importaciones'

    id_importacion = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    nombre_archivo = db.Column(db.String(255))
    hash_archivo = db.Column(db.String(64), index=True)
    estado = db.Column(db.String(20), nullable=False, default='aplicada')
    dias = db.Column(db.Integer, nullable=False, default=0)
    pedidos = db.Column(db.Integer, nullable=False, default=0)
    total = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    fecha_desde = db.Column(db.Date)
    fecha_hasta = db.Column(db.Date)
    sesiones_json = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_reversion = db.Column(db.DateTime)

    registros = db.relationship(
        'GastronomiaImportacionRegistro',
        backref='importacion',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    @property
    def sesiones_ids(self) -> list[int]:
        try:
            return [int(item) for item in json.loads(self.sesiones_json or '[]')]
        except (TypeError, ValueError):
            return []

    @sesiones_ids.setter
    def sesiones_ids(self, valores) -> None:
        self.sesiones_json = json.dumps([int(item) for item in valores or []])

    def to_dict(self):
        return {
            'id_importacion': self.id_importacion,
            'nombre_archivo': self.nombre_archivo,
            'estado': self.estado,
            'dias': int(self.dias or 0),
            'pedidos': int(self.pedidos or 0),
            'total': float(self.total or 0),
            'fecha_desde': self.fecha_desde.isoformat() if self.fecha_desde else None,
            'fecha_hasta': self.fecha_hasta.isoformat() if self.fecha_hasta else None,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
        }


class GastronomiaImportacionRegistro(db.Model):
    """Pedido y venta creados por una importacion."""
    __tablename__ = 'gastronomia_importacion_registros'

    id_registro = db.Column(db.Integer, primary_key=True)
    importacion_id = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_importaciones.id_importacion', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    pedido_id = db.Column(db.Integer, nullable=False, index=True)
    venta_id = db.Column(db.Integer, nullable=True, index=True)


class GastronomiaImportAlias(db.Model):
    """Diccionario aprendido: como escribe el local cada producto en su Excel."""
    __tablename__ = 'gastronomia_import_alias'

    id_alias = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    alias = db.Column(db.String(160), nullable=False)
    producto_id = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_productos.id_producto', ondelete='CASCADE'),
        nullable=False,
    )
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'alias', name='uq_gastronomia_import_alias_cliente'),
    )
