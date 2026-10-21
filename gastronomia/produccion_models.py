"""Modelos de produccion diaria, porciones y merma de producto terminado.

Trabajan sobre el `stock_disponible` que ya tiene el producto del menu (no hay
un segundo stock): cada registro guarda el stock anterior y el nuevo para
auditoria. Diseno en docs/pasteleria_fase3_diseno.md.
"""
from datetime import datetime

from app import db


TIPO_PRODUCCION = 'produccion'
TIPO_MERMA = 'merma'
TIPO_AJUSTE = 'ajuste'
TIPO_APERTURA = 'apertura'
TIPO_PORCIONES = 'porciones'
TIPOS_REGISTRO = (TIPO_PRODUCCION, TIPO_MERMA, TIPO_AJUSTE, TIPO_APERTURA, TIPO_PORCIONES)

MOTIVO_FALTANTE = 'faltante'
MOTIVOS_MERMA = {
    'vencido': 'Vencido',
    'golpeado': 'Golpeado / roto',
    'regalado': 'Regalado',
    'consumo_propio': 'Consumo propio',
    MOTIVO_FALTANTE: 'Faltante sin explicar',
    'otro': 'Otro',
}


class GastronomiaProduccionRegistro(db.Model):
    """Movimiento de stock de producto terminado (tanda, merma, ajuste o apertura)."""

    __tablename__ = 'gastronomia_produccion_registros'

    id_registro = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    producto_id = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_productos.id_producto', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    # Dia local del negocio al que corresponde el movimiento.
    fecha = db.Column(db.Date, nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False, index=True)
    cantidad = db.Column(db.Integer, nullable=False)
    motivo = db.Column(db.String(30), nullable=True)
    stock_anterior = db.Column(db.Integer, nullable=False)
    stock_nuevo = db.Column(db.Integer, nullable=False)
    # Costo de receta por unidad al momento del registro (NULL si no tiene receta).
    costo_unitario = db.Column(db.Numeric(15, 2), nullable=True)
    # Une la fila del entero y la de las porciones de una misma apertura.
    referencia = db.Column(db.String(40), nullable=True, index=True)
    observacion = db.Column(db.String(255), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True, index=True)
    fecha_registro = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    producto = db.relationship('GastronomiaProducto')

    def to_dict(self) -> dict:
        return {
            'id_registro': self.id_registro,
            'producto_id': self.producto_id,
            'producto': getattr(self.producto, 'nombre', None),
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'tipo': self.tipo,
            'cantidad': int(self.cantidad or 0),
            'motivo': self.motivo,
            'motivo_label': MOTIVOS_MERMA.get(self.motivo or '', None),
            'stock_anterior': int(self.stock_anterior or 0),
            'stock_nuevo': int(self.stock_nuevo or 0),
            'costo_unitario': float(self.costo_unitario) if self.costo_unitario is not None else None,
            'referencia': self.referencia,
            'observacion': self.observacion,
            'usuario_id': self.usuario_id,
        }


class GastronomiaProductoPorcion(db.Model):
    """Relacion torta entera -> producto porcion (1 entero = N porciones)."""

    __tablename__ = 'gastronomia_producto_porciones'

    id_relacion = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    producto_entero_id = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_productos.id_producto', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    producto_porcion_id = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_productos.id_producto', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    porciones = db.Column(db.Integer, nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    entero = db.relationship('GastronomiaProducto', foreign_keys=[producto_entero_id])
    porcion = db.relationship('GastronomiaProducto', foreign_keys=[producto_porcion_id])

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'producto_entero_id', name='uq_gastronomia_porcion_entero'),
    )

    def to_dict(self) -> dict:
        return {
            'id_relacion': self.id_relacion,
            'producto_entero_id': self.producto_entero_id,
            'producto_porcion_id': self.producto_porcion_id,
            'porcion': getattr(self.porcion, 'nombre', None),
            'porciones': int(self.porciones or 0),
            'activo': bool(self.activo),
        }
