"""Modelos de encargos (pedidos programados con sena y fotos de referencia).

Los pedidos y sus items reciben columnas nuevas por mixin para no engordar
`gastronomia/models.py`. Todo es opcional: un pedido comun tiene `es_encargo`
en falso y el resto en NULL. Diseno en docs/pasteleria_fase1_diseno.md.
"""
from datetime import datetime

from app import db


ADELANTO_VIGENTE = 'vigente'
ADELANTO_APLICADO = 'aplicado'
ADELANTO_DEVUELTO = 'devuelto'
ADELANTO_RETENIDO = 'retenido'
ESTADOS_ADELANTO = (ADELANTO_VIGENTE, ADELANTO_APLICADO, ADELANTO_DEVUELTO, ADELANTO_RETENIDO)


class PedidoEncargoMixin:
    """Columnas de encargo para `GastronomiaPedido`."""

    es_encargo = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    # Hora local del negocio, tal como la carga el operador (no UTC).
    fecha_programada = db.Column(db.DateTime, nullable=True, index=True)


class PedidoItemEncargoMixin:
    """Columnas de encargo para `GastronomiaPedidoItem`."""

    texto_personalizado = db.Column(db.String(240), nullable=True)


class GastronomiaPedidoAdelanto(db.Model):
    """Sena (adelanto) cobrada por un encargo."""

    __tablename__ = 'gastronomia_pedido_adelantos'

    id_adelanto = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    pedido_id = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_pedidos.id_pedido', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False, index=True)
    id_sesion_caja = db.Column(db.Integer, db.ForeignKey('sesiones_caja.id_sesion'), nullable=True, index=True)
    # Solo existe cuando la sena fue en efectivo: es lo unico que mueve la caja.
    id_movimiento_caja = db.Column(db.Integer, db.ForeignKey('movimientos_caja.id_movimiento_caja'), nullable=True)
    id_metodo_pago = db.Column(db.Integer, db.ForeignKey('metodos_pago.id_metodo_pago'), nullable=True)
    metodo_pago = db.Column(db.String(40), nullable=False, default='efectivo')
    referencia = db.Column(db.String(100))
    monto = db.Column(db.Numeric(15, 2), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default=ADELANTO_VIGENTE, server_default=ADELANTO_VIGENTE, index=True)
    monto_devuelto = db.Column(db.Numeric(15, 2), nullable=False, default=0, server_default='0')
    id_movimiento_devolucion = db.Column(db.Integer, db.ForeignKey('movimientos_caja.id_movimiento_caja'), nullable=True)
    id_venta = db.Column(db.Integer, db.ForeignKey('ventas.id_venta'), nullable=True)
    observacion = db.Column(db.String(255))
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_resolucion = db.Column(db.DateTime, nullable=True)
    id_sesion_resolucion = db.Column(db.Integer, db.ForeignKey('sesiones_caja.id_sesion'), nullable=True, index=True)
    usuario_resolucion_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True)

    pedido = db.relationship('GastronomiaPedido', backref=db.backref('adelantos', lazy='dynamic'))

    __table_args__ = (
        db.CheckConstraint('monto > 0', name='ck_gastronomia_adelanto_monto_positivo'),
        db.CheckConstraint('monto_devuelto >= 0 AND monto_devuelto <= monto', name='ck_gastronomia_adelanto_devuelto'),
    )

    @property
    def monto_retenido(self):
        if self.estado != ADELANTO_RETENIDO:
            return 0
        return float(self.monto or 0) - float(self.monto_devuelto or 0)

    def to_dict(self):
        return {
            'id_adelanto': self.id_adelanto,
            'pedido_id': self.pedido_id,
            'metodo_pago': self.metodo_pago,
            'referencia': self.referencia,
            'monto': float(self.monto or 0),
            'estado': self.estado,
            'monto_devuelto': float(self.monto_devuelto or 0),
            'monto_retenido': self.monto_retenido,
            'observacion': self.observacion,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'fecha_resolucion': self.fecha_resolucion.isoformat() if self.fecha_resolucion else None,
        }


class GastronomiaPedidoFoto(db.Model):
    """Foto de referencia adjunta a un encargo."""

    __tablename__ = 'gastronomia_pedido_fotos'

    id_foto = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    pedido_id = db.Column(
        db.Integer,
        db.ForeignKey('gastronomia_pedidos.id_pedido', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True)
    url = db.Column(db.String(500), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    pedido = db.relationship('GastronomiaPedido', backref=db.backref('fotos', lazy='dynamic'))

    def to_dict(self):
        return {
            'id_foto': self.id_foto,
            'pedido_id': self.pedido_id,
            'url': self.url,
            'orden': int(self.orden or 0),
        }
