"""Resolucion del negocio operativo para Tienda Online."""

from flask_login import current_user

from app import db
from app.models.cliente import Cliente
from app.models.tienda import TiendaConfig
from gastronomia.models import GastronomiaClienteConfig, GastronomiaProducto
from gastronomia.services.modo_operacion import asegurar_cliente_operativo_gastronomia, gastronomia_activa


DEFAULT_STORE_CLIENT_NAME = 'Negocio principal'
DEFAULT_STORE_CLIENT_RUC = 'tienda-default'


def resolver_cliente_tienda(data: dict | None = None, *, crear_si_falta: bool = False) -> int | None:
    if gastronomia_activa():
        cliente_gastronomia = resolver_cliente_gastronomia_tienda()
        if cliente_gastronomia:
            return cliente_gastronomia

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


def buscar_config_tienda_admin(data: dict | None = None, id_cliente: int | None = None) -> TiendaConfig | None:
    config = _config_desde_data(data or {})
    if config:
        return config

    if id_cliente:
        config = (
            TiendaConfig.query
            .filter(TiendaConfig.id_cliente == int(id_cliente))
            .order_by(TiendaConfig.id_config.asc())
            .first()
        )
        if config:
            return config

    configs = (
        TiendaConfig.query
        .filter(TiendaConfig.activa.is_(True))
        .order_by(TiendaConfig.id_config.asc())
        .limit(2)
        .all()
    )
    if len(configs) == 1:
        return configs[0]
    return None


def resolver_cliente_gastronomia_tienda(config: TiendaConfig | None = None) -> int | None:
    cliente_config = _cliente_gastronomia_para_config(config)
    if cliente_config:
        return cliente_config

    activos = (
        GastronomiaClienteConfig.query
        .filter(GastronomiaClienteConfig.gastronomia_activo.is_(True))
        .order_by(GastronomiaClienteConfig.id_config.asc())
        .limit(2)
        .all()
    )
    if len(activos) == 1:
        return int(activos[0].cliente_id)

    productos_cliente = (
        db.session.query(GastronomiaProducto.cliente_id)
        .filter(GastronomiaProducto.activo.is_(True))
        .distinct()
        .order_by(GastronomiaProducto.cliente_id.asc())
        .limit(2)
        .all()
    )
    if len(productos_cliente) == 1:
        return int(productos_cliente[0][0])

    cliente_bootstrap = asegurar_cliente_operativo_gastronomia(
        usuario_id=getattr(current_user, 'id_usuario', None),
    )
    if cliente_bootstrap:
        return int(cliente_bootstrap)

    if config and config.id_cliente:
        return int(config.id_cliente)
    return None


def _cliente_gastronomia_para_config(config: TiendaConfig | None) -> int | None:
    if not config or not config.id_cliente:
        return None
    config_gastro = GastronomiaClienteConfig.query.filter_by(cliente_id=int(config.id_cliente)).first()
    if config_gastro and bool(config_gastro.gastronomia_activo):
        return int(config.id_cliente)
    return None


def _id_cliente_usuario() -> int | None:
    try:
        id_cliente = int(getattr(current_user, 'id_cliente', 0) or 0)
    except (TypeError, ValueError):
        return None
    return id_cliente if id_cliente > 0 else None


def _cliente_desde_config(data: dict) -> int | None:
    config = _config_desde_data(data)
    if config:
        return int(config.id_cliente)

    configs = TiendaConfig.query.order_by(TiendaConfig.id_config.asc()).limit(2).all()
    if len(configs) == 1:
        return int(configs[0].id_cliente)
    return None


def _config_desde_data(data: dict) -> TiendaConfig | None:
    id_config_raw = data.get('id_config')
    try:
        id_config = int(id_config_raw)
    except (TypeError, ValueError):
        id_config = None
    if id_config:
        config = TiendaConfig.query.filter_by(id_config=id_config).first()
        if config:
            return config

    slug_actual = str(data.get('slug_actual') or data.get('slug') or '').strip().lower()
    if slug_actual:
        config = TiendaConfig.query.filter_by(slug=slug_actual).first()
        if config:
            return config
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
