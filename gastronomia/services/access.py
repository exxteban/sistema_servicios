"""Control de acceso para pantallas y APIs gastronomicas."""
from flask_login import current_user

from app.models import Cliente
from gastronomia.models import GastronomiaClienteConfig
from gastronomia.services.modo_operacion import gastronomia_activa


def _puede_resolver_contexto_operativo_unico() -> bool:
    if not getattr(current_user, 'is_authenticated', False):
        return False
    if getattr(current_user, 'es_admin', lambda: False)():
        return True
    return bool(getattr(current_user, 'tiene_permiso', lambda _codigo: False)('gastronomia_acceso'))


def _cliente_id_config_unico(*, solo_gastronomia_activa: bool) -> int | None:
    query = GastronomiaClienteConfig.query
    if solo_gastronomia_activa:
        query = query.filter(GastronomiaClienteConfig.gastronomia_activo.is_(True))

    configs = (
        query
        .order_by(GastronomiaClienteConfig.id_config.asc())
        .limit(2)
        .all()
    )
    if len(configs) != 1:
        return None

    try:
        cliente_id = int(configs[0].cliente_id or 0)
    except (TypeError, ValueError):
        return None
    return cliente_id if cliente_id > 0 else None


def _cliente_id_unico_gastronomia() -> int | None:
    if not _puede_resolver_contexto_operativo_unico():
        return None

    cliente_id = _cliente_id_config_unico(solo_gastronomia_activa=True)
    if cliente_id:
        return cliente_id

    configs = (
        GastronomiaClienteConfig.query
        .order_by(GastronomiaClienteConfig.id_config.asc())
        .limit(2)
        .all()
    )
    if len(configs) > 1:
        return None
    if len(configs) == 1:
        return _cliente_id_config_unico(solo_gastronomia_activa=False)

    clientes = (
        Cliente.query
        .filter(Cliente.activo.is_(True), Cliente.id_cliente != 1)
        .order_by(Cliente.id_cliente.asc())
        .limit(2)
        .all()
    )
    if len(clientes) != 1:
        return None

    try:
        cliente_id = int(clientes[0].id_cliente or 0)
    except (TypeError, ValueError):
        return None
    return cliente_id if cliente_id > 0 else None


def cliente_id_actual_gastronomia() -> int | None:
    if not gastronomia_activa():
        return None
    try:
        cliente_id = int(getattr(current_user, 'id_cliente', 0) or 0)
    except (TypeError, ValueError):
        return _cliente_id_unico_gastronomia()
    if cliente_id <= 0:
        return _cliente_id_unico_gastronomia()
    return cliente_id


def mensaje_contexto_gastronomia() -> str:
    if not gastronomia_activa():
        return 'Gastronomia no esta activa en esta instalacion.'
    return 'Este usuario no tiene un contexto operativo asignado para Gastronomia.'
