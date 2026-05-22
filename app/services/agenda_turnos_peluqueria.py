from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.models import Servicio


SERVICIOS_TURNO_PELUQUERIA_BASE = (
    {'id': 'corte', 'nombre': 'Corte', 'duracion': 30, 'icono': 'fas fa-cut'},
    {'id': 'barba', 'nombre': 'Barba', 'duracion': 20, 'icono': 'fas fa-user'},
    {'id': 'corte_barba', 'nombre': 'Corte + barba', 'duracion': 45, 'icono': 'fas fa-user-tie'},
    {'id': 'color', 'nombre': 'Color', 'duracion': 90, 'icono': 'fas fa-palette'},
    {'id': 'peinado', 'nombre': 'Peinado', 'duracion': 45, 'icono': 'fas fa-wind'},
    {'id': 'lavado', 'nombre': 'Lavado', 'duracion': 20, 'icono': 'fas fa-shower'},
    {'id': 'otro', 'nombre': 'Otro servicio', 'duracion': 30, 'icono': 'fas fa-plus'},
)

TURNO_PELUQUERIA_TIPO_IDS = tuple(item['id'] for item in SERVICIOS_TURNO_PELUQUERIA_BASE)
TURNO_PELUQUERIA_TIPO_LABELS = {item['id']: item['nombre'] for item in SERVICIOS_TURNO_PELUQUERIA_BASE}


def _normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize('NFKD', value or '')
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', ' ', ascii_text.lower()).strip()


def _parse_positive_int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def infer_turno_peluqueria_tipo_from_title(title: str | None) -> str | None:
    normalized_title = _normalize_text(title)
    if not normalized_title:
        return None
    for item in SERVICIOS_TURNO_PELUQUERIA_BASE:
        normalized_name = _normalize_text(item['nombre'])
        if normalized_title == normalized_name or normalized_title.startswith(f'{normalized_name} '):
            return item['id']
    return None


def _find_catalog_service_by_turno_tipo(turno_tipo_id: str | None) -> Servicio | None:
    turno_tipo_id = (turno_tipo_id or '').strip().lower()
    if turno_tipo_id not in TURNO_PELUQUERIA_TIPO_LABELS:
        return None

    servicio = (
        Servicio.query
        .filter(
            Servicio.activo.is_(True),
            Servicio.turno_rapido_tipo == turno_tipo_id,
        )
        .order_by(Servicio.id_servicio.asc())
        .first()
    )
    if servicio is not None:
        return servicio

    keyword = _normalize_text(TURNO_PELUQUERIA_TIPO_LABELS[turno_tipo_id])
    if not keyword:
        return None
    candidatos = Servicio.query.filter(Servicio.activo.is_(True)).order_by(Servicio.id_servicio.asc()).all()
    matches = []
    for candidato in candidatos:
        nombre = _normalize_text(candidato.nombre)
        if not nombre:
            continue
        if keyword in nombre or nombre in keyword:
            matches.append(candidato)
    return matches[0] if len(matches) == 1 else None


def resolve_turno_peluqueria_catalog_service(*, servicio_id=None, turno_tipo_id=None, title=None) -> Servicio | None:
    servicio = get_turno_peluqueria_catalog_service(servicio_id)
    if servicio is not None:
        return servicio
    inferred_tipo = (turno_tipo_id or '').strip().lower() or infer_turno_peluqueria_tipo_from_title(title)
    return _find_catalog_service_by_turno_tipo(inferred_tipo)


def build_turno_peluqueria_services() -> list[dict[str, Any]]:
    servicios_catalogo = (
        Servicio.query
        .filter(
            Servicio.activo.is_(True),
            Servicio.turno_rapido_tipo.in_(TURNO_PELUQUERIA_TIPO_IDS),
        )
        .order_by(Servicio.turno_rapido_tipo.asc(), Servicio.id_servicio.asc())
        .all()
    )
    servicios_por_tipo = {}
    for servicio in servicios_catalogo:
        clave = (servicio.turno_rapido_tipo or '').strip().lower()
        if clave and clave not in servicios_por_tipo:
            servicios_por_tipo[clave] = servicio

    servicios = []
    for item in SERVICIOS_TURNO_PELUQUERIA_BASE:
        servicio_catalogo = servicios_por_tipo.get(item['id']) or _find_catalog_service_by_turno_tipo(item['id'])
        servicios.append({
            **item,
            'catalogo_id': int(servicio_catalogo.id_servicio) if servicio_catalogo else None,
            'catalogo_nombre': (servicio_catalogo.nombre or '').strip() if servicio_catalogo else '',
        })
    return servicios


def get_turno_peluqueria_catalog_service(servicio_id) -> Servicio | None:
    servicio_id = _parse_positive_int(servicio_id)
    if not servicio_id:
        return None
    return Servicio.query.filter_by(id_servicio=servicio_id, activo=True).first()


def build_pos_data_from_agenda_turno(*, cliente_id=None, servicio_id=None, vendedor_id=None) -> dict[str, Any] | None:
    servicio = get_turno_peluqueria_catalog_service(servicio_id)
    cliente_id = _parse_positive_int(cliente_id)
    vendedor_id = _parse_positive_int(vendedor_id)

    items = []
    if servicio is not None:
        precio = float(servicio.precio or 0)
        items.append({
            'tipo': 'servicio',
            'id': int(servicio.id_servicio),
            'id_servicio': int(servicio.id_servicio),
            'codigo': (servicio.codigo or '').strip(),
            'nombre': (servicio.nombre or '').strip(),
            'precio': precio,
            'precio_base': precio,
            'cantidad': 1,
            'es_servicio': True,
            'stock': 0,
            'stock_minimo': 0,
            'iva': int(servicio.porcentaje_iva or 0),
            'precio_manual': False,
        })

    if not items and not cliente_id and not vendedor_id:
        return None

    return {
        'cliente_id': cliente_id,
        'id_usuario_vendedor': vendedor_id,
        'items': items,
    }
