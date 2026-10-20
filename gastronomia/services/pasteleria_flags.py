"""Lectura de los flags de pasteleria/cafeteria de un cliente."""
from __future__ import annotations

from gastronomia.config_flags import (
    FOTOS_ENCARGO_DEFAULT,
    OPCIONES_CANCELACION,
    PASTELERIA_FLAGS,
)
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


def parametros_encargos(cliente_id: int | None) -> dict:
    """Parametros de encargos del cliente; sin configuracion rige el comportamiento base."""
    config = None
    try:
        cliente_id_int = int(cliente_id or 0)
    except (TypeError, ValueError):
        cliente_id_int = 0
    if cliente_id_int > 0:
        config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id_int).first()
    opciones = _opciones_validas(getattr(config, 'encargos_cancelacion_opciones', None))
    max_fotos = getattr(config, 'encargos_max_fotos', None)
    return {
        'anticipo_horas': max(0, int(getattr(config, 'encargos_anticipo_horas', 0) or 0)),
        'max_por_dia': getattr(config, 'encargos_max_por_dia', None) or None,
        'max_fotos': FOTOS_ENCARGO_DEFAULT if max_fotos is None else max(0, int(max_fotos)),
        'opciones_cancelacion': opciones,
    }


def _opciones_validas(valor) -> list[str]:
    pedidas = [parte.strip() for parte in str(valor or '').split(',') if parte.strip()]
    validas = [opcion for opcion in OPCIONES_CANCELACION if opcion in pedidas]
    return validas or list(OPCIONES_CANCELACION)
