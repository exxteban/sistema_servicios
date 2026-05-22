from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models import Servicio, ServicioPrecioOpcion


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


def _money_label(value) -> str:
    return f"Gs. {'{:,.0f}'.format(value or 0).replace(',', '.')}"


def _catalog_service_price_options(servicio: Servicio | None) -> list[dict[str, Any]]:
    if servicio is None:
        return []
    opciones = (
        servicio.opciones
        .filter_by(activo=True)
        .order_by(ServicioPrecioOpcion.orden.asc(), ServicioPrecioOpcion.id_opcion_precio.asc())
        .all()
    )
    return [
        {
            'id': int(opcion.id_opcion_precio),
            'servicio_id': int(servicio.id_servicio),
            'etiqueta': (opcion.etiqueta or '').strip(),
            'costo': float(opcion.costo or 0),
            'costo_label': _money_label(opcion.costo or 0),
            'precio': float(opcion.precio or 0),
            'precio_label': _money_label(opcion.precio or 0),
        }
        for opcion in opciones
    ]


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


def _matches_turno_tipo(servicio: Servicio, turno_tipo_id: str) -> bool:
    turno_tipo_id = (turno_tipo_id or '').strip().lower()
    label = TURNO_PELUQUERIA_TIPO_LABELS.get(turno_tipo_id, '')
    normalized_label = _normalize_text(label)
    if not normalized_label:
        return False
    if (servicio.turno_rapido_tipo or '').strip().lower() == turno_tipo_id:
        return True
    categoria = _normalize_text(servicio.categoria)
    nombre = _normalize_text(servicio.nombre)
    return categoria == normalized_label or nombre == normalized_label or nombre.startswith(f'{normalized_label} ')


def _catalog_services_for_turno_tipo(turno_tipo_id: str) -> list[Servicio]:
    if turno_tipo_id not in TURNO_PELUQUERIA_TIPO_LABELS:
        return []
    candidatos = Servicio.query.filter(Servicio.activo.is_(True)).order_by(Servicio.id_servicio.asc()).all()
    return [servicio for servicio in candidatos if _matches_turno_tipo(servicio, turno_tipo_id)]


def _catalog_service_variants_for_turno_tipo(turno_tipo_id: str) -> list[dict[str, Any]]:
    variantes = []
    for servicio in _catalog_services_for_turno_tipo(turno_tipo_id):
        opciones = _catalog_service_price_options(servicio)
        if opciones:
            variantes.extend(opciones)
            continue
        variantes.append({
            'id': f'servicio-{int(servicio.id_servicio)}',
            'servicio_id': int(servicio.id_servicio),
            'etiqueta': (servicio.nombre or '').strip(),
            'costo': float(servicio.costo or 0),
            'costo_label': _money_label(servicio.costo or 0),
            'precio': float(servicio.precio or 0),
            'precio_label': _money_label(servicio.precio or 0),
            'es_base': True,
        })
    return variantes


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
        variantes = _catalog_service_variants_for_turno_tipo(item['id'])
        servicios.append({
            **item,
            'catalogo_id': int(servicio_catalogo.id_servicio) if servicio_catalogo else None,
            'catalogo_nombre': (servicio_catalogo.nombre or '').strip() if servicio_catalogo else '',
            'catalogo_costo': float(servicio_catalogo.costo or 0) if servicio_catalogo else 0,
            'catalogo_costo_label': _money_label(servicio_catalogo.costo or 0) if servicio_catalogo else '',
            'catalogo_precio': float(servicio_catalogo.precio or 0) if servicio_catalogo else 0,
            'catalogo_precio_label': _money_label(servicio_catalogo.precio or 0) if servicio_catalogo else '',
            'catalogo_opciones': variantes,
        })
    return servicios


def get_turno_peluqueria_catalog_service(servicio_id) -> Servicio | None:
    servicio_id = _parse_positive_int(servicio_id)
    if not servicio_id:
        return None
    return Servicio.query.filter_by(id_servicio=servicio_id, activo=True).first()


def get_turno_peluqueria_catalog_price_option(servicio: Servicio | None, price_option_id) -> ServicioPrecioOpcion | None:
    option_id = _parse_positive_int(price_option_id)
    if servicio is None or not option_id:
        return None
    return ServicioPrecioOpcion.query.filter_by(
        id_opcion_precio=option_id,
        id_servicio=servicio.id_servicio,
        activo=True,
    ).first()


def parse_turno_manual_price(value) -> Decimal | None:
    if value in (None, ''):
        return None
    try:
        normalized = str(value).replace(',', '.').strip()
        amount = Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None
    return amount if amount > 0 else None


def is_turno_peluqueria_catalog_service_chargeable(servicio: Servicio | None) -> bool:
    if servicio is None:
        return False
    try:
        return float(servicio.precio or 0) > 0
    except Exception:
        return False


def is_turno_peluqueria_catalog_price_option_chargeable(price_option: ServicioPrecioOpcion | None) -> bool:
    if price_option is None:
        return False
    try:
        return float(price_option.precio or 0) > 0
    except Exception:
        return False


def catalog_service_requires_price_option(servicio: Servicio | None) -> bool:
    return bool(_catalog_service_price_options(servicio))


def is_turno_peluqueria_pos_chargeable(servicio: Servicio | None, manual_price=None, price_option: ServicioPrecioOpcion | None = None) -> bool:
    if servicio is None:
        return False
    manual_amount = parse_turno_manual_price(manual_price)
    if manual_amount is not None:
        return True
    if price_option is not None:
        return is_turno_peluqueria_catalog_price_option_chargeable(price_option)
    return is_turno_peluqueria_catalog_service_chargeable(servicio)


def build_turno_peluqueria_chargeable_catalog_services() -> list[dict[str, Any]]:
    servicios = (
        Servicio.query
        .filter(
            Servicio.activo.is_(True),
            Servicio.precio > 0,
        )
        .order_by(Servicio.nombre.asc(), Servicio.id_servicio.asc())
        .all()
    )
    return [
        {
            'id': int(servicio.id_servicio),
            'nombre': (servicio.nombre or '').strip(),
            'costo': float(servicio.costo or 0),
            'costo_label': _money_label(servicio.costo or 0),
            'precio': float(servicio.precio or 0),
            'precio_label': _money_label(servicio.precio or 0),
            'precios_opciones': _catalog_service_price_options(servicio),
        }
        for servicio in servicios
    ]


def build_pos_data_from_agenda_turno(*, cliente_id=None, servicio_id=None, vendedor_id=None, actividad_id=None, manual_price=None, title=None, price_option_id=None) -> dict[str, Any] | None:
    servicio = get_turno_peluqueria_catalog_service(servicio_id)
    price_option = get_turno_peluqueria_catalog_price_option(servicio, price_option_id)
    cliente_id = _parse_positive_int(cliente_id)
    vendedor_id = _parse_positive_int(vendedor_id)
    actividad_id = _parse_positive_int(actividad_id)
    manual_amount = parse_turno_manual_price(manual_price)

    items = []
    if is_turno_peluqueria_pos_chargeable(servicio, manual_amount, price_option=price_option):
        precio_base_raw = price_option.precio if price_option is not None else (servicio.precio or 0)
        precio = float(manual_amount if manual_amount is not None else precio_base_raw)
        precio_base = float(precio_base_raw or precio) if servicio is not None else precio
        items.append({
            'tipo': 'servicio',
            'id': int(servicio.id_servicio),
            'id_servicio': int(servicio.id_servicio),
            'codigo': (servicio.codigo or '').strip(),
            'nombre': (str(title or '').strip() or (servicio.nombre or '').strip()),
            'precio': precio,
            'precio_base': precio_base,
            'cantidad': 1,
            'es_servicio': True,
            'stock': 0,
            'stock_minimo': 0,
            'iva': int(servicio.porcentaje_iva or 0),
            'precio_manual': manual_amount is not None,
            'precio_opcion_id': int(price_option.id_opcion_precio) if price_option is not None else None,
        })

    if not items and not cliente_id and not vendedor_id and not actividad_id:
        return None

    return {
        'agenda_actividad_id': actividad_id,
        'cliente_id': cliente_id,
        'id_usuario_vendedor': vendedor_id,
        'items': items,
    }
