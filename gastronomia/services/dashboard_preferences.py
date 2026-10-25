"""Preferencias del dashboard operativo de Gastronomia."""
from __future__ import annotations

import json
from typing import Any


DASHBOARD_CARD_ORDER_PREF_KEY = 'gastronomia_dashboard_cards_order'

# El orden guardado por el usuario se respeta dentro de cada grupo.
_DASHBOARD_GROUPS = (
    {'id': 'operacion', 'title': 'Operacion en vivo', 'icon': 'fas fa-bolt'},
    {'id': 'pedidos', 'title': 'Pedidos y ventas', 'icon': 'fas fa-receipt'},
    {'id': 'analisis', 'title': 'Analisis y produccion', 'icon': 'fas fa-chart-simple'},
)

_DASHBOARD_CARD_DEFINITIONS = (
    {
        'id': 'pedidos_tienda',
        'group': 'pedidos',
        'permission': 'pos',
        'title': 'Pedidos tienda',
        'description': 'Pedidos web pendientes de contactar y confirmar.',
        'alert_description': 'Hay pedidos de tienda esperando confirmacion.',
        'endpoint': 'gastronomia.pedidos_tienda',
        'icon': 'fas fa-store',
    },
    {
        'id': 'pos',
        'group': 'operacion',
        'featured': True,
        'permission': 'pos',
        'title': 'POS Touch',
        'description': 'Toma rapida de pedidos para mesa o mostrador.',
        'endpoint': 'gastronomia.pos',
        'icon': 'fas fa-tablet-alt',
    },
    {
        'id': 'encargos',
        'group': 'pedidos',
        'permission': 'encargos',
        'title': 'Encargos',
        'description': 'Tortas y pedidos programados: sena, fotos y produccion por dia.',
        'endpoint': 'gastronomia.encargos',
        'icon': 'fas fa-cake-candles',
    },
    {
        'id': 'produccion',
        'group': 'analisis',
        'permission': 'produccion',
        'title': 'Produccion',
        'description': 'Tandas del dia, abrir tortas en porciones, cierre y merma.',
        'endpoint': 'gastronomia.produccion',
        'icon': 'fas fa-bread-slice',
    },
    {
        'id': 'delivery',
        'group': 'operacion',
        'permission': 'pos',
        'title': 'Delivery',
        'description': 'Tablero activo, contacto, ticket y seguimiento publico.',
        'endpoint': 'gastronomia.delivery',
        'icon': 'fas fa-motorcycle',
    },
    {
        'id': 'salon',
        'group': 'operacion',
        'permission': 'salon',
        'title': 'Salon',
        'description': 'Mesas, ocupacion y movimientos.',
        'endpoint': 'gastronomia.salon',
        'icon': 'fas fa-chair',
    },
    {
        'id': 'cocina',
        'group': 'operacion',
        'permission': 'cocina',
        'title': 'Cocina',
        'description': 'Pantalla KDS para pedidos pendientes.',
        'endpoint': 'gastronomia.cocina',
        'icon': 'fas fa-fire',
    },
    {
        'id': 'delivery_ruta',
        'group': 'operacion',
        'permission': 'delivery',
        'title': 'Mi ruta delivery',
        'description': 'Pedidos asignados, salida y confirmacion de entrega.',
        'endpoint': 'gastronomia.delivery_ruta',
        'icon': 'fas fa-route',
    },
    {
        'id': 'caja',
        'group': 'operacion',
        'permission': 'caja',
        'title': 'Caja',
        'description': 'Cobro y cierre del flujo operativo.',
        'alert_description': 'Hay pedidos sin cobrar esperando en caja.',
        'endpoint': 'gastronomia.caja',
        'icon': 'fas fa-cash-register',
    },
    {
        'id': 'ventas',
        'group': 'pedidos',
        'permission': 'ventas',
        'title': 'Ventas',
        'description': 'Historial del dia: anular, facturar y emitir notas de credito.',
        'endpoint': 'ventas.listar',
        'icon': 'fas fa-receipt',
    },
    {
        'id': 'entregas',
        'group': 'pedidos',
        'permission': 'entregas',
        'title': 'Entregas',
        'description': 'Pedidos entregados por dia y estado de pago.',
        'endpoint': 'gastronomia.entregas',
        'icon': 'fas fa-truck-ramp-box',
    },
    {
        'id': 'reportes',
        'group': 'analisis',
        'permission': 'reportes',
        'title': 'Reportes',
        'description': 'Ventas, productos y tiempos de cocina.',
        'endpoint': 'gastronomia.reportes',
        'icon': 'fas fa-chart-line',
    },
    {
        'id': 'bi',
        'group': 'analisis',
        'permission': 'reportes',
        'title': 'BI Gastronomia',
        'description': 'Radar de menu, stock, horarios bajos y decisiones comerciales.',
        'endpoint': 'inteligencia.dashboard',
        'endpoint_params': {'vista': 'gastronomia'},
        'icon': 'fas fa-chart-pie',
    },
)


def build_dashboard_cards(
    user: Any,
    permisos: dict[str, bool],
    *,
    contexto_operativo: bool,
    pedidos_pendientes_caja: int = 0,
    pedidos_pendientes_tienda: int = 0,
) -> list[dict]:
    available = [
        _build_card(definition, contexto_operativo, pedidos_pendientes_caja, pedidos_pendientes_tienda)
        for definition in _DASHBOARD_CARD_DEFINITIONS
        if permisos.get(definition['permission'])
    ]
    return _sort_cards(available, _load_order_ids(user))


def build_dashboard_groups(cards: list[dict], badges: dict[str, dict] | None = None) -> list[dict]:
    """Agrupa las tarjetas ya ordenadas y les adjunta su badge en vivo."""
    badges = badges or {}
    groups = []
    for group in _DASHBOARD_GROUPS:
        group_cards = [
            {**card, 'badge': badges.get(card['id'])}
            for card in cards
            if card.get('group') == group['id']
        ]
        if group_cards:
            groups.append({**group, 'cards': group_cards})
    return groups


def set_dashboard_card_order(user: Any, card_ids: list[str] | None, permisos: dict[str, bool]) -> list[str]:
    allowed_ids = [
        definition['id']
        for definition in _DASHBOARD_CARD_DEFINITIONS
        if permisos.get(definition['permission'])
    ]
    order = _normalize_order(allowed_ids, card_ids)
    user.set_preferencia(DASHBOARD_CARD_ORDER_PREF_KEY, json.dumps(order, ensure_ascii=False))
    return order


def _build_card(definition: dict, contexto_operativo: bool, pedidos_pendientes_caja: int, pedidos_pendientes_tienda: int) -> dict:
    card = dict(definition)
    card['disabled'] = not contexto_operativo
    card['alert_count'] = int(pedidos_pendientes_caja or 0) if card['id'] == 'caja' else 0
    if card['id'] == 'pedidos_tienda':
        card['alert_count'] = int(pedidos_pendientes_tienda or 0)
    if card['alert_count'] > 0:
        card['description'] = card.get('alert_description') or card['description']
    return card


def _load_order_ids(user: Any) -> list[str] | None:
    try:
        raw = user.get_preferencia(DASHBOARD_CARD_ORDER_PREF_KEY, '') or ''
    except Exception:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    return [str(item) for item in data]


def _sort_cards(cards: list[dict], requested_ids: list[str] | None) -> list[dict]:
    allowed_ids = [card['id'] for card in cards]
    order = _normalize_order(allowed_ids, requested_ids)
    by_id = {card['id']: card for card in cards}
    return [by_id[card_id] for card_id in order if card_id in by_id]


def _normalize_order(allowed_ids: list[str], requested_ids: list[str] | None) -> list[str]:
    allowed = set(allowed_ids)
    order = []
    seen = set()
    for card_id in requested_ids or []:
        normalized = str(card_id or '').strip()
        if normalized in allowed and normalized not in seen:
            order.append(normalized)
            seen.add(normalized)
    for card_id in allowed_ids:
        if card_id not in seen:
            order.append(card_id)
    return order
