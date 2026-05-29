"""Resolucion del negocio operativo para Tienda Online."""

from flask_login import current_user

from app import db
from app.models.cliente import Cliente
from app.models.tienda import TiendaConfig
from gastronomia.services.modo_operacion import asegurar_cliente_operativo_gastronomia


DEFAULT_STORE_CLIENT_NAME = 'Negocio principal'
DEFAULT_STORE_CLIENT_RUC = 'tienda-default'


def resolver_cliente_tienda(data: dict | None = None, *, crear_si_falta: bool = False) -> int | None:
    usuario_cliente_id = _id_cliente_usuario()
    if usuario_cliente_id:
        return usuario_cliente_id

    data = data or {}
    cliente_por_config = _cliente_desde_config(data)
    if cliente_por_config:
        return cliente_por_config

    cliente_gastronomia = asegurar_cliente_operativo_gastronomia(
        usuario_id=getattr(current_user, 'id_usuario', None),
    )
    if cliente_gastronomia:
        return cliente_gastronomia

    cliente_unico = _cliente_operativo_unico()
    if cliente_unico:
        return cliente_unico

    if crear_si_falta:
        return _crear_cliente_operativo()

    return None


def _id_cliente_usuario() -> int | None:
    try:
        id_cliente = int(getattr(current_user, 'id_cliente', 0) or 0)
    except (TypeError, ValueError):
        return None
    return id_cliente if id_cliente > 0 else None


def _cliente_desde_config(data: dict) -> int | None:
    id_config_raw = data.get('id_config')
    try:
        id_config = int(id_config_raw)
    except (TypeError, ValueError):
        id_config = None
    if id_config:
        config = TiendaConfig.query.filter_by(id_config=id_config).first()
        if config:
            return int(config.id_cliente)

    slug_actual = str(data.get('slug_actual') or data.get('slug') or '').strip().lower()
    if slug_actual:
        config = TiendaConfig.query.filter_by(slug=slug_actual, activa=True).first()
        if config:
            return int(config.id_cliente)

    configs = TiendaConfig.query.order_by(TiendaConfig.id_config.asc()).limit(2).all()
    if len(configs) == 1:
        return int(configs[0].id_cliente)
    return None


def _cliente_operativo_unico() -> int | None:
    clientes = (
        Cliente.query
        .filter(Cliente.activo.is_(True), Cliente.id_cliente != 1)
        .order_by(Cliente.id_cliente.asc())
        .limit(2)
        .all()
    )
    if len(clientes) != 1:
        return None
    return int(clientes[0].id_cliente)


def _crear_cliente_operativo() -> int:
    cliente = (
        Cliente.query
        .filter(Cliente.id_cliente != 1, Cliente.ruc_ci == DEFAULT_STORE_CLIENT_RUC)
        .order_by(Cliente.id_cliente.asc())
        .first()
    )
    if cliente:
        cliente.activo = True
    else:
        cliente = Cliente(
            nombre=DEFAULT_STORE_CLIENT_NAME,
            ruc_ci=DEFAULT_STORE_CLIENT_RUC,
            tipo='minorista',
            activo=True,
            notas='Cliente operativo automatico para Tienda Online en instalacion local.',
        )
        db.session.add(cliente)
        db.session.flush()
    db.session.commit()
    return int(cliente.id_cliente)
