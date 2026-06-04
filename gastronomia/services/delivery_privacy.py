"""Privacidad de localizacion para delivery gastronomico."""
from __future__ import annotations

from app.models import Configuracion
from app.services.ia_backoffice.security import es_usuario_root


CLAVE_DELIVERY_LOCALIZACION_SOLO_ROOT = 'gastro_delivery_localizacion_solo_root'
DESC_DELIVERY_LOCALIZACION_SOLO_ROOT = 'Restringe ubicacion GPS y destino exacto de delivery al usuario root'
_CAMPOS_LOCALIZACION_PEDIDO = (
    'ubicacion_entrega_url',
    'destino_latitud',
    'destino_longitud',
    'ultima_ubicacion_delivery',
)


def localizacion_delivery_solo_root_activa() -> bool:
    return Configuracion.obtener_bool(CLAVE_DELIVERY_LOCALIZACION_SOLO_ROOT, default=False)


def puede_ver_localizacion_delivery(user=None) -> bool:
    return not localizacion_delivery_solo_root_activa() or es_usuario_root(user)


def ocultar_localizacion_objeto(value, user=None):
    if puede_ver_localizacion_delivery(user):
        return value
    return _filtrar_localizacion(value)


def ocultar_localizacion_pedido(pedido: dict, user=None) -> dict:
    return ocultar_localizacion_objeto(pedido, user)


def ocultar_localizacion_pedidos(pedidos: list[dict], user=None) -> list[dict]:
    return ocultar_localizacion_objeto(pedidos, user)


def ocultar_localizacion_eventos(eventos: list[dict], user=None) -> list[dict]:
    return ocultar_localizacion_objeto(eventos, user)


def _filtrar_localizacion(value):
    if isinstance(value, list):
        return [_filtrar_localizacion(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _filtrar_localizacion(item)
        for key, item in value.items()
        if key not in _CAMPOS_LOCALIZACION_PEDIDO
    }
