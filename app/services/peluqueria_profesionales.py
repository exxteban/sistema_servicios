"""Quiénes aparecen como profesionales en turnos, agenda del día y dashboard de servicios.

Si nadie está marcado con "Atiende clientes" se muestran todos (comportamiento de siempre);
apenas se marca alguno, solo aparecen los marcados.
"""
from __future__ import annotations

from flask import has_request_context, request

from app.models import Usuario


def hay_profesionales_marcados() -> bool:
    cache = request.environ if has_request_context() else {}
    if 'peluqueria.profesionales_marcados' not in cache:
        cache['peluqueria.profesionales_marcados'] = (
            Usuario.query.filter(Usuario.atiende_clientes.is_(True), Usuario.activo.is_(True)).first() is not None
        )
    return cache['peluqueria.profesionales_marcados']


def filtrar_query_profesionales(query):
    if not hay_profesionales_marcados():
        return query
    return query.filter(Usuario.atiende_clientes.is_(True))


def filtrar_profesionales(usuarios: list) -> list:
    if not hay_profesionales_marcados():
        return list(usuarios)
    return [usuario for usuario in usuarios if getattr(usuario, 'atiende_clientes', None) is True]
