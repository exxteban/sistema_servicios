"""Lectura y escritura del modo operativo global de Gastronomia."""
from __future__ import annotations

from app import db
from app.models import Cliente, Configuracion
from gastronomia.models import GastronomiaClienteConfig


MODO_SERVICIOS = 'servicios'
MODO_GASTRONOMIA = 'gastronomia'
MODOS_OPERACION = (MODO_SERVICIOS, MODO_GASTRONOMIA)
CLAVE_MODO_OPERACION_PRINCIPAL = 'modo_operacion_principal'
DESC_MODO_OPERACION_PRINCIPAL = 'Modo operativo principal de la instalacion'
CLIENTE_OPERATIVO_DEFAULT_NOMBRE = 'Negocio principal'
CLIENTE_OPERATIVO_DEFAULT_RUC = 'gastro-default'


def normalizar_modo_operacion(valor: str | None) -> str:
    modo = (valor or '').strip().lower()
    return modo if modo in MODOS_OPERACION else MODO_SERVICIOS


def _obtener_config_legacy(cliente_id: int | None, *, crear: bool = False) -> GastronomiaClienteConfig | None:
    """Compatibilidad con configuraciones antiguas por cliente."""
    try:
        cliente_id_int = int(cliente_id or 0)
    except (TypeError, ValueError):
        return None
    if cliente_id_int <= 0:
        return None

    config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id_int).first()
    if config or not crear:
        return config

    config = GastronomiaClienteConfig(
        cliente_id=cliente_id_int,
        modo_operacion=MODO_SERVICIOS,
        gastronomia_activo=False,
    )
    db.session.add(config)
    return config


def obtener_modo_operacion() -> str:
    modo = Configuracion.obtener(CLAVE_MODO_OPERACION_PRINCIPAL, None)
    if modo is not None:
        return normalizar_modo_operacion(modo)

    legacy = (
        GastronomiaClienteConfig.query
        .order_by(
            GastronomiaClienteConfig.fecha_modificacion.desc(),
            GastronomiaClienteConfig.id_config.desc(),
        )
        .first()
    )
    return normalizar_modo_operacion(getattr(legacy, 'modo_operacion', None))


def gastronomia_activa() -> bool:
    return obtener_modo_operacion() == MODO_GASTRONOMIA


def _asegurar_config_gastronomia_activa(cliente_id: int, *, usuario_id: int | None = None) -> None:
    config = GastronomiaClienteConfig.query.filter_by(cliente_id=cliente_id).first()
    if not config:
        config = GastronomiaClienteConfig(
            cliente_id=cliente_id,
            modo_operacion=MODO_GASTRONOMIA,
            gastronomia_activo=True,
            actualizado_por_id=usuario_id,
        )
        db.session.add(config)
        return

    config.modo_operacion = MODO_GASTRONOMIA
    config.gastronomia_activo = True
    if usuario_id:
        config.actualizado_por_id = usuario_id


def asegurar_cliente_operativo_gastronomia(*, usuario_id: int | None = None) -> int | None:
    """Auto-bootstrap para instalaciones monocliente sin negocio operativo cargado."""
    if not gastronomia_activa():
        return None

    clientes = (
        Cliente.query
        .filter(Cliente.activo.is_(True), Cliente.id_cliente != 1)
        .order_by(Cliente.id_cliente.asc())
        .limit(2)
        .all()
    )
    if len(clientes) > 1:
        return None

    if len(clientes) == 1:
        try:
            cliente_id = int(clientes[0].id_cliente or 0)
        except (TypeError, ValueError):
            return None
        if cliente_id <= 0:
            return None
        _asegurar_config_gastronomia_activa(cliente_id, usuario_id=usuario_id)
        db.session.commit()
        return cliente_id

    cliente = (
        Cliente.query
        .filter(Cliente.id_cliente != 1, Cliente.ruc_ci == CLIENTE_OPERATIVO_DEFAULT_RUC)
        .order_by(Cliente.id_cliente.asc())
        .first()
    )
    if not cliente:
        cliente = Cliente(
            nombre=CLIENTE_OPERATIVO_DEFAULT_NOMBRE,
            ruc_ci=CLIENTE_OPERATIVO_DEFAULT_RUC,
            tipo='minorista',
            activo=True,
            notas='Bootstrap automatico para Gastronomia en instalacion monocliente.',
        )
        db.session.add(cliente)
        db.session.flush()
    else:
        cliente.activo = True
        if not (cliente.nombre or '').strip():
            cliente.nombre = CLIENTE_OPERATIVO_DEFAULT_NOMBRE
        if not (cliente.tipo or '').strip():
            cliente.tipo = 'minorista'

    try:
        cliente_id = int(cliente.id_cliente or 0)
    except (TypeError, ValueError):
        db.session.rollback()
        return None
    if cliente_id <= 0:
        db.session.rollback()
        return None

    _asegurar_config_gastronomia_activa(cliente_id, usuario_id=usuario_id)
    db.session.commit()
    return cliente_id


def obtener_config_cliente(cliente_id: int | None, *, crear: bool = False) -> GastronomiaClienteConfig | None:
    return _obtener_config_legacy(cliente_id, crear=crear)


def obtener_modo_operacion_cliente(cliente_id: int | None) -> str:
    modo_global = Configuracion.obtener(CLAVE_MODO_OPERACION_PRINCIPAL, None)
    if modo_global is not None:
        return normalizar_modo_operacion(modo_global)
    config = _obtener_config_legacy(cliente_id)
    if not config:
        return MODO_SERVICIOS
    return normalizar_modo_operacion(config.modo_operacion)


def gastronomia_activa_para_cliente(cliente_id: int | None) -> bool:
    return obtener_modo_operacion_cliente(cliente_id) == MODO_GASTRONOMIA


def establecer_modo_operacion(
    modo_operacion: str | None,
    *,
    usuario_id: int | None = None,
) -> dict:
    modo = normalizar_modo_operacion(modo_operacion)
    Configuracion.establecer(
        CLAVE_MODO_OPERACION_PRINCIPAL,
        modo,
        descripcion=DESC_MODO_OPERACION_PRINCIPAL,
    )
    if modo == MODO_GASTRONOMIA:
        asegurar_cliente_operativo_gastronomia(usuario_id=usuario_id)
    return {
        'modo_operacion': modo,
        'gastronomia_activo': modo == MODO_GASTRONOMIA,
        'actualizado_por_id': usuario_id,
    }


def establecer_modo_operacion_cliente(
    cliente_id: int | None,
    modo_operacion: str | None,
    *,
    usuario_id: int | None = None,
) -> GastronomiaClienteConfig:
    modo = normalizar_modo_operacion(modo_operacion)
    establecer_modo_operacion(modo, usuario_id=usuario_id)

    if not cliente_id:
        return {
            'modo_operacion': modo,
            'gastronomia_activo': modo == MODO_GASTRONOMIA,
            'cliente_id': None,
        }

    try:
        cliente_id_int = int(cliente_id or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError('Cliente invalido para configurar Gastronomia.') from exc

    cliente = db.session.get(Cliente, cliente_id_int)
    if not cliente or not getattr(cliente, 'activo', True):
        raise ValueError('Cliente inexistente o inactivo.')
    if getattr(cliente, 'es_consumidor_final', False):
        raise ValueError('No se puede configurar Gastronomia para Consumidor Final.')

    config = _obtener_config_legacy(cliente_id_int, crear=True)
    config.modo_operacion = modo
    config.gastronomia_activo = modo == MODO_GASTRONOMIA
    config.actualizado_por_id = usuario_id
    db.session.commit()
    return config


def listar_clientes_con_modo() -> list[dict]:
    modo = obtener_modo_operacion()
    return [{
        'cliente': None,
        'modo_operacion': modo,
        'gastronomia_activo': modo == MODO_GASTRONOMIA,
    }]
