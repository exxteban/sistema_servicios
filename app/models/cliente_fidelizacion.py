from datetime import datetime

from app import db


class ClienteFidelizacionMovimiento(db.Model):
    __tablename__ = 'clientes_fidelizacion_movimientos'

    id_movimiento = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(
        db.Integer,
        db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True, index=True)
    tipo_movimiento = db.Column(db.String(40), nullable=False, index=True)
    delta_compras_acumuladas = db.Column(db.Integer, nullable=False, default=0)
    delta_consumos_disponibles = db.Column(db.Integer, nullable=False, default=0)
    delta_consumos_canjeados = db.Column(db.Integer, nullable=False, default=0)
    beneficio_tipo = db.Column(db.String(40), index=True)
    beneficio_valor = db.Column(db.Numeric(15, 2))
    beneficio_descripcion = db.Column(db.String(255), default='')
    beneficio_fecha_vencimiento = db.Column(db.Date, index=True)
    referencia_tipo = db.Column(db.String(40), index=True)
    referencia_id = db.Column(db.Integer, index=True)
    id_movimiento_origen = db.Column(
        db.Integer,
        db.ForeignKey('clientes_fidelizacion_movimientos.id_movimiento'),
        nullable=True,
        index=True,
    )
    descripcion = db.Column(db.String(255), nullable=False, default='')
    fecha_movimiento = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    usuario = db.relationship('Usuario')
    movimiento_origen = db.relationship(
        'ClienteFidelizacionMovimiento',
        remote_side=[id_movimiento],
        foreign_keys=[id_movimiento_origen],
    )

    def __repr__(self):
        return f'<ClienteFidelizacionMovimiento {self.id_movimiento} cliente={self.id_cliente}>'
