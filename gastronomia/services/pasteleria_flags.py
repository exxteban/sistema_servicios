"""Lectura de los flags de pasteleria/cafeteria de un cliente."""
from __future__ import annotations

from gastronomia.config_flags import PASTELERIA_FLAGS
from gastronomia.models import GastronomiaClienteConfig


def flag_activo(cliente_id: int | None, flag: str) -> bool:
    """True solo si la configuracion del cliente existe y el flag esta encendido."""
    if flag not in PASTELERIA_FLAGS:
        raise ValueError(f'Flag de pasteleria desconocido: {flag}')
    try:
        cliente_id_int = int(cliente_id or 0)
    except (TypeError, ValueError):
        return False
    if cliente_id_int <= 0:
        return False
    config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id_int).first()
    return bool(config and getattr(config, flag, False))


def flags_cliente(cliente_id: int | None) -> dict[str, bool]:
    return {flag: flag_activo(cliente_id, flag) for flag in PASTELERIA_FLAGS}
