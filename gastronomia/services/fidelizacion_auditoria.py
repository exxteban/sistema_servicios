"""Auditoria de fichas de cliente por celular (fase 1 del plan de BI).

Las fichas creadas antes de la tabla `gastronomia_bi_fichas_telefono` no tienen fila por celular. Esta
auditoria registra la fila de cada celular que tiene una sola ficha y lista los celulares repetidos,
que nunca se asignan solos: el dueño decide a quien dejar.
"""
from __future__ import annotations

from collections import defaultdict

from app import db
from app.models import Cliente
from gastronomia.bi_models import GastronomiaBiFichaTelefono
from gastronomia.services.bi.identidad import telefono_normalizado


def auditar_fichas_telefono(cliente_id: int, registrar: bool = True) -> dict:
    """Devuelve {'registradas': n, 'duplicados': {telefono: [id_cliente, ...]}}."""
    por_telefono = defaultdict(list)
    for cliente in Cliente.query.filter(Cliente.id_cliente != 1, Cliente.telefono.isnot(None)).all():
        telefono = telefono_normalizado(cliente.telefono)
        if telefono:
            por_telefono[telefono].append(cliente)
    existentes = {
        fila.telefono_normalizado
        for fila in GastronomiaBiFichaTelefono.query.filter_by(cliente_id=int(cliente_id)).all()
    }
    registradas = 0
    for telefono, fichas in por_telefono.items():
        if len(fichas) != 1 or telefono in existentes:
            continue
        registradas += 1
        if registrar:
            db.session.add(GastronomiaBiFichaTelefono(
                cliente_id=int(cliente_id),
                telefono_normalizado=telefono,
                id_cliente_ficha=int(fichas[0].id_cliente),
            ))
    if registrar:
        db.session.commit()
    duplicados = {t: [c.id_cliente for c in fichas] for t, fichas in por_telefono.items() if len(fichas) > 1}
    return {'registradas': registradas, 'duplicados': duplicados}
