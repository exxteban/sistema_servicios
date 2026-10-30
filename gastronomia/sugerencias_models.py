"""Tablas aditivas del sugeridor; no modifican pedidos ni cobros existentes."""
from datetime import datetime

from app import db


class ClienteMixin:
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente', ondelete='CASCADE'), nullable=False, index=True)


class GastronomiaSugerenciaPar(ClienteMixin, db.Model):
    __tablename__ = 'gastronomia_sugerencias_par'
    id = db.Column(db.Integer, primary_key=True)
    nivel = db.Column(db.String(20), nullable=False, default='producto')
    id_origen = db.Column(db.Integer, nullable=False)
    id_destino = db.Column(db.Integer, nullable=False)
    soporte = db.Column(db.Integer, nullable=False, default=0)
    confianza = db.Column(db.Float, nullable=False, default=0)
    lift = db.Column(db.Float, nullable=False, default=0)
    puntaje = db.Column(db.Float, nullable=False, default=0)
    calculado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'nivel', 'id_origen', 'id_destino', name='uq_gs_par'),
        db.Index('ix_gs_par_busqueda', 'cliente_id', 'nivel', 'id_origen', 'puntaje'),
    )


class GastronomiaSugerenciaOrigen(ClienteMixin, db.Model):
    __tablename__ = 'gastronomia_sugerencias_origen'
    id = db.Column(db.Integer, primary_key=True)
    nivel = db.Column(db.String(20), nullable=False, default='producto')
    id_origen = db.Column(db.Integer, nullable=False)
    pedidos = db.Column(db.Integer, nullable=False, default=0)
    __table_args__ = (db.UniqueConstraint('cliente_id', 'nivel', 'id_origen', name='uq_gs_origen'),)


class GastronomiaSugerenciaRegla(ClienteMixin, db.Model):
    __tablename__ = 'gastronomia_sugerencias_regla'
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False, default='forzar')
    origen_tipo = db.Column(db.String(20), nullable=False, default='cualquiera')
    origen_id = db.Column(db.Integer, nullable=True)
    destino_tipo = db.Column(db.String(20), nullable=False, default='producto')
    destino_id = db.Column(db.Integer, nullable=False)
    prioridad = db.Column(db.Integer, nullable=False, default=0)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    creado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class GastronomiaSugerenciaExcluido(ClienteMixin, db.Model):
    __tablename__ = 'gastronomia_sugerencias_excluido'
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False, default='producto')
    id_ref = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint('cliente_id', 'tipo', 'id_ref', name='uq_gs_excluido'),)


class GastronomiaSugerenciaConfig(ClienteMixin, db.Model):
    __tablename__ = 'gastronomia_sugerencias_config'
    id = db.Column(db.Integer, primary_key=True)
    activo = db.Column(db.Boolean, nullable=False, default=False)
    mostrar_en_pos = db.Column(db.Boolean, nullable=False, default=False)
    max_franja = db.Column(db.Integer, nullable=False, default=3)
    __table_args__ = (
        db.UniqueConstraint('cliente_id', name='uq_gs_config'),
        db.CheckConstraint('max_franja BETWEEN 1 AND 3', name='ck_gs_max_franja'),
    )


class GastronomiaSugerenciaCalculo(ClienteMixin, db.Model):
    __tablename__ = 'gastronomia_sugerencias_calculo'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(32), nullable=True)
    inicio = db.Column(db.DateTime, nullable=True)
    fin = db.Column(db.DateTime, nullable=True)
    pedidos = db.Column(db.Integer, nullable=False, default=0)
    pares = db.Column(db.Integer, nullable=False, default=0)
    error = db.Column(db.String(500), nullable=True)
    __table_args__ = (db.UniqueConstraint('cliente_id', name='uq_gs_calculo'),)
