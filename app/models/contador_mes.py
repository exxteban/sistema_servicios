"""Lo que el/la contador/a carga o decide por mes: saldo anterior, retenciones, presentado.

El resto del resumen se calcula; esto no se puede calcular y se carga a mano.
Al marcar el mes presentado se guarda una foto del débito y el crédito: si
después alguien carga o corrige algo de ese mes, la pantalla muestra qué
cambió. No bloquea nada: avisa. Tabla nueva, un registro por mes ('2026-09').
"""
from datetime import datetime

from app import db


class ContadorMes(db.Model):
    __tablename__ = 'contador_meses'

    id = db.Column(db.Integer, primary_key=True)
    periodo = db.Column(db.String(7), nullable=False, unique=True)
    saldo_favor_anterior = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    retenciones = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    presentado = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    presentado_en = db.Column(db.DateTime)
    id_usuario_presentado = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'))
    debito_presentado = db.Column(db.Numeric(15, 2))
    credito_presentado = db.Column(db.Numeric(15, 2))
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario_presentado = db.relationship('Usuario')

    def __repr__(self):
        return f'<ContadorMes {self.periodo}>'
