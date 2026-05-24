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
