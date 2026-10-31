"""Tablas de la cola de envio asistido y de la telemetria del BI de gastronomia (BI-02).

Son tablas nuevas y aditivas: create_all() las crea en las instalaciones existentes.
No modifican pedidos, cobros ni clientes finales.
"""
from datetime import datetime

from app import db


class GastronomiaBiContacto(db.Model):
    """Contacto de la cola ya tocado por el dueno. Clave: cliente, telefono, segmento y ultimo pedido."""
    __tablename__ = 'gastronomia_bi_contactos'

    id_contacto = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    telefono_normalizado = db.Column(db.String(30), nullable=False)
    nombre = db.Column(db.String(120), nullable=False, default='Cliente')
    segmento = db.Column(db.String(30), nullable=False)
    ultimo_pedido_id = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='abierto')
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    fecha_estado = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            'cliente_id', 'telefono_normalizado', 'segmento', 'ultimo_pedido_id',
            name='uq_gastro_bi_contacto_ventana',
        ),
        db.Index('ix_gastro_bi_contacto_estado', 'cliente_id', 'estado', 'fecha_estado'),
    )


class GastronomiaBiNoContactar(db.Model):
    """Telefono que pidio no recibir mensajes. Sale de todas las colas del cliente."""
    __tablename__ = 'gastronomia_bi_no_contactar'

    id_preferencia = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    telefono_normalizado = db.Column(db.String(30), nullable=False)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'telefono_normalizado', name='uq_gastro_bi_no_contactar'),
    )


class GastronomiaBiEvento(db.Model):
    """Telemetria minima del BI: acciones iniciadas, completadas y omitidas."""
    __tablename__ = 'gastronomia_bi_eventos'

    id_evento = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)
    tipo = db.Column(db.String(30), nullable=False)
    segmento = db.Column(db.String(30), nullable=False, default='')
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.Index('ix_gastro_bi_evento_tipo', 'cliente_id', 'tipo', 'fecha'),
    )
