"""Servicios del catálogo tal como se muestran en los botones del alta de turno."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func

from app.models import Servicio, ServicioPrecioOpcion
from app.services.agenda_turnos_peluqueria import SERVICIOS_TURNO_PELUQUERIA_BASE
from app.utils.helpers import formato_moneda_local


ICONO_SERVICIO_DEFAULT = 'fas fa-cut'
_ICONOS_POR_TIPO = {item['id']: item['icono'] for item in SERVICIOS_TURNO_PELUQUERIA_BASE}


def _precio(valor) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _opciones_servicio(servicio: Servicio) -> list[dict[str, Any]]:
    opciones = (
        servicio.opciones
        .filter_by(activo=True)
        .order_by(ServicioPrecioOpcion.orden.asc(), ServicioPrecioOpcion.id_opcion_precio.asc())
        .all()
    )
    return [
        {
            'id': int(opcion.id_opcion_precio),
            'etiqueta': (opcion.etiqueta or '').strip(),
            'precio': _precio(opcion.precio),
            'precio_label': formato_moneda_local(opcion.precio),
        }
        for opcion in opciones
    ]


def _serializar_servicio(servicio: Servicio) -> dict[str, Any]:
    tipo = (servicio.turno_rapido_tipo or '').strip().lower()
    precio = _precio(servicio.precio)
    return {
        'id': int(servicio.id_servicio),
        'nombre': (servicio.nombre or '').strip(),
        'precio': precio,
        'precio_label': formato_moneda_local(precio) if precio > 0 else '',
        'duracion': int(servicio.duracion_minutos or 30),
        'tipo': tipo,
        'icono': _ICONOS_POR_TIPO.get(tipo, ICONO_SERVICIO_DEFAULT),
        'opciones': _opciones_servicio(servicio),
    }


def build_turno_peluqueria_catalogo() -> list[dict[str, Any]]:
    """Servicios activos con precio, duración y variantes; vacío si el catálogo no tiene servicios."""
    servicios = (
        Servicio.query
        .filter(Servicio.activo.is_(True))
        .order_by(func.lower(Servicio.nombre).asc(), Servicio.id_servicio.asc())
        .all()
    )
    return [_serializar_servicio(servicio) for servicio in servicios]
