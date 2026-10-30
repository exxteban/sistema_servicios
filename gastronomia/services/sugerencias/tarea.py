"""Recálculo explícito con candado atómico y reemplazo transaccional por cliente.

Usar en una sesión sin cambios pendientes; nunca desde el guardado del pedido.
"""
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from gastronomia.models import GastronomiaClienteConfig
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaCalculo as Estado, GastronomiaSugerenciaOrigen as Origen,
    GastronomiaSugerenciaPar as Par,
)
from gastronomia.services.sugerencias import constantes as C
from gastronomia.services.sugerencias.diagnostico import analizar
from gastronomia.services.sugerencias.aprendizaje import actualizar


def recalcular(cliente_id, ahora=None, *, solo_si_vencido=False):
    ahora = ahora or datetime.utcnow()
    if not GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id, gastronomia_activo=True).first():
        raise ValueError('Gastronomía no está activa para este cliente.')
    if not Estado.query.filter_by(cliente_id=cliente_id).first():
        try:
            db.session.add(Estado(cliente_id=cliente_id))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    token = uuid4().hex
    consulta = Estado.query.filter(
        Estado.cliente_id == cliente_id,
        or_(Estado.token.is_(None), Estado.inicio < ahora - timedelta(minutes=C.CANDADO_VENCE_MINUTOS)),
    )
    if solo_si_vencido:
        consulta = consulta.filter(or_(
            Estado.fin.is_(None),
            Estado.fin <= ahora - timedelta(hours=C.RECALCULAR_CADA_HORAS),
        ))
    adquirido = consulta.update({'token': token, 'inicio': ahora, 'error': None}, synchronize_session=False)
    db.session.commit()
    if not adquirido:
        return False
    try:
        resultado = analizar(cliente_id, ahora)
        # Termina la lectura antes de tomar el bloqueo de escritura (SQLite/WAL).
        db.session.rollback()
        cantidad = sum(len(filas) for filas in resultado['pares'].values())
        # UPDATE condicionado: también protege SQLite, que ignora FOR UPDATE.
        publicado = Estado.query.filter_by(cliente_id=cliente_id, token=token).update(
            {'token': None, 'fin': ahora, 'pedidos': resultado['pedidos'], 'pares': cantidad},
            synchronize_session=False,
        )
        if not publicado:
            db.session.rollback()
            return False
        Par.query.filter_by(cliente_id=cliente_id).delete(synchronize_session=False)
        Origen.query.filter_by(cliente_id=cliente_id).delete(synchronize_session=False)
        for nivel, filas in resultado['pares'].items():
            for fila in filas:
                db.session.add(Par(cliente_id=cliente_id, calculado_en=ahora, **fila))
            for origen, pedidos in resultado['conteos'][nivel].crudo.items():
                db.session.add(Origen(cliente_id=cliente_id, nivel=nivel, id_origen=origen, pedidos=pedidos))
        actualizar(cliente_id, ahora)
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        Estado.query.filter_by(cliente_id=cliente_id, token=token).update(
            {'token': None, 'error': str(exc)[:500]}, synchronize_session=False,
        )
        db.session.commit()
        raise
