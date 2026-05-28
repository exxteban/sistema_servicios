"""Consultas reutilizables para mesas gastronomicas."""
from __future__ import annotations

from gastronomia.models import GastronomiaMesa


def obtener_mesa_activa_por_nombre(cliente_id: int, nombre: str) -> GastronomiaMesa | None:
    nombre = (nombre or '').strip()[:40]
    if not nombre:
        return None
    return GastronomiaMesa.query.filter(
        GastronomiaMesa.cliente_id == int(cliente_id),
        GastronomiaMesa.nombre == nombre,
        GastronomiaMesa.activo.is_(True),
    ).first()
