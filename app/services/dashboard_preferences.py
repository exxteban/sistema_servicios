from __future__ import annotations

import json
from typing import Any

from flask import url_for
from werkzeug.routing import BuildError

from app.services.system_modules import CLAVE_MODULO_SERVICIO_TECNICO, system_module_enabled
from flujo_caja import CLAVE_MODULO_FLUJO_CAJA


DASHBOARD_VIEW_CLASSIC = 'classic'
DASHBOARD_VIEW_NEW = 'new'
DASHBOARD_VIEW_PREF_KEY = 'dashboard_view'
DASHBOARD_QUICK_ACTIONS_PREF_KEY = 'dashboard_quick_actions'
DASHBOARD_QUICK_ACTION_SLOTS = 4


def normalize_dashboard_view(value: str | None) -> str:
    value = (value or '').strip().lower()
    if value == DASHBOARD_VIEW_NEW:
        return DASHBOARD_VIEW_NEW
    return DASHBOARD_VIEW_CLASSIC


def get_dashboard_view_preference(user: Any) -> str:
    return normalize_dashboard_view(_get_preference(user, DASHBOARD_VIEW_PREF_KEY, DASHBOARD_VIEW_CLASSIC))


def set_dashboard_view_preference(user: Any, value: str | None) -> str:
    view = normalize_dashboard_view(value)
    user.set_preferencia(DASHBOARD_VIEW_PREF_KEY, view)
    return view


def get_dashboard_quick_actions(user: Any) -> tuple[list[dict], list[dict]]:
    available = _build_available_actions(user)
    selected_ids = _load_action_ids(user)
    selected = _select_actions(available, selected_ids)
    return available, selected


def set_dashboard_quick_actions(user: Any, action_ids: list[str] | None) -> tuple[list[dict], list[dict]]:
    available = _build_available_actions(user)
    selected = _select_actions(available, (action_ids or [])[:20])
    user.set_preferencia(
        DASHBOARD_QUICK_ACTIONS_PREF_KEY,
        json.dumps([action['id'] for action in selected], ensure_ascii=False),
    )
    return available, selected


def _build_available_actions(user: Any) -> list[dict]:
    sales_action = _build_sales_action(user)
    definitions = [
        sales_action,
        _action('productos', 'Productos', 'Inventario y catalogo', 'Inventario', 'fas fa-box',
                'bg-emerald-600', 'productos.listar', _can_any(user, 'ver_inventario', 'ver_productos')),
        _action('nuevo_producto', 'Nuevo producto', 'Agregar al inventario', 'Alta', 'fas fa-plus-circle',
                'bg-emerald-600', 'productos.nuevo', _can(user, 'crear_producto')),
        _action('compras', 'Compras', 'Cargar mercaderia', 'Stock', 'fas fa-truck',
                'bg-purple-600', 'compras.nueva', _can(user, 'crear_compra')),
        _action('reportes', 'Reportes', 'Metricas del negocio', 'Datos', 'fas fa-chart-line',
                'bg-orange-500', 'reportes.index', _can(user, 'ver_reportes')),
        _action('gastos_corrientes', 'Gastos Corrientes', 'Vencimientos y pagos', 'Control',
                'fas fa-file-invoice-dollar', 'bg-amber-500', 'gastos_corrientes.index',
                _is_admin(user) or _can(user, 'ver_gastos_corrientes')),
        _action('flujo_caja', 'Flujo Proyectado', 'Tesoreria semanal', 'Pro',
                'fas fa-chart-line', 'bg-cyan-600', 'flujo_caja.index',
                _module_enabled(CLAVE_MODULO_FLUJO_CAJA, default=True)
                and (_is_admin(user) or _can(user, 'ver_flujo_caja'))),
        _action('inteligencia', 'Inteligencia', 'Alertas y oportunidades', 'BI', 'fas fa-brain',
                'bg-indigo-600', 'inteligencia.dashboard', _is_admin(user) or _can(user, 'ver_reportes')),
        _action('servicio_tecnico', 'Servicio Tecnico', 'Reparaciones y estados', 'Taller', 'fas fa-tools',
                'bg-rose-600', 'reparaciones.listar',
                _module_enabled(CLAVE_MODULO_SERVICIO_TECNICO, default=True) and _can(user, 'ver_reparaciones')),
        _action('pedidos', 'Pedidos', 'Gestion de pedidos', 'Clientes', 'fas fa-clipboard-list',
                'bg-blue-600 dark:bg-blue-500', 'pedidos.listar',
                _is_admin(user) or _can_any(user, 'ver_clientes', 'crear_cliente', 'editar_cliente')),
        _action('caja', 'Caja', 'Estado y cierres', 'Finanzas', 'fas fa-wallet',
                'bg-slate-700', 'caja.estado', _can(user, 'ver_caja')),
        _action('agenda', 'Agenda', 'Actividades del dia', 'Tareas', 'fas fa-calendar-check',
                'bg-violet-600', 'agenda.dashboard', _can(user, 'agenda_acceso')),
        _action('cobranzas', 'Cobranzas', 'Cuentas y cobros', 'Credito', 'fas fa-hand-holding-usd',
                'bg-teal-600', 'cobranzas.index',
                _module_enabled('cobranzas_activo') and (_is_admin(user) or _can(user, 'ver_cobranzas'))),
        _action('control_empleados', 'Control Empleados', 'Asistencia y pagos', 'Equipo', 'fas fa-users-cog',
                'bg-sky-600', 'control_empleados.index',
                _module_enabled('control_empleados_activo')
                and (_is_admin(user) or _can_any(user, 'ver_control_empleados', 'gestionar_control_empleados'))),
        _action('clientes', 'Clientes', 'Base de clientes', 'CRM', 'fas fa-users',
                'bg-lime-600', 'clientes.listar', _can(user, 'ver_clientes')),
        _action('proveedores', 'Proveedores', 'Compras y contactos', 'Compras', 'fas fa-address-card',
                'bg-stone-600', 'proveedores.listar', _can(user, 'ver_proveedores')),
    ]
    return [action for action in definitions if action]


def _build_sales_action(user: Any) -> dict | None:
    if not _can(user, 'crear_venta'):
        return None

    if _should_use_vendor_sales_register(user):
        return _action(
            'ventas',
            'Registro vendedor',
            'Enviar venta a caja',
            'Manual',
            'fas fa-clipboard-list',
            'bg-amber-500',
            'ventas.registro_vendedor',
            True,
        )

    return _action(
        'ventas',
        'Nueva venta',
        'Cobrar en pocos pasos',
        'POS',
        'fas fa-cash-register',
        'bg-blue-600',
        'ventas.pos',
        True,
    )


def _action(
    action_id: str,
    title: str,
    subtitle: str,
    badge: str,
    icon: str,
    color_class: str,
    endpoint: str,
    enabled: bool,
) -> dict | None:
    if not enabled:
        return None
    try:
        href = url_for(endpoint)
    except BuildError:
        return None
    return {
        'id': action_id,
        'title': title,
        'subtitle': subtitle,
        'badge': badge,
        'icon': icon,
        'color_class': color_class,
        'href': href,
        'tab_url': href,
        'tab_title': title,
        'tab_icon': icon,
    }


def _select_actions(available: list[dict], requested_ids: list[str]) -> list[dict]:
    by_id = {action['id']: action for action in available}
    selected = []
    seen = set()
    for action_id in requested_ids:
        normalized = str(action_id or '').strip()
        if normalized in by_id and normalized not in seen:
            selected.append(by_id[normalized])
            seen.add(normalized)
        if len(selected) >= DASHBOARD_QUICK_ACTION_SLOTS:
            return selected

    for action in available:
        if action['id'] not in seen:
            selected.append(action)
            seen.add(action['id'])
        if len(selected) >= DASHBOARD_QUICK_ACTION_SLOTS:
            break
    return selected


def _load_action_ids(user: Any) -> list[str]:
    raw = _get_preference(user, DASHBOARD_QUICK_ACTIONS_PREF_KEY, '')
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def _get_preference(user: Any, key: str, default: str = '') -> str:
    try:
        return str(user.get_preferencia(key, default) or default)
    except Exception:
        return default


def _module_enabled(key: str, default: bool = False) -> bool:
    try:
        return system_module_enabled(key, default=default)
    except Exception:
        return default


def _should_use_vendor_sales_register(user: Any) -> bool:
    modo_cobro_exclusivo = (
        _module_enabled('caja_flujo_enviado_desde_vendedor')
        and _module_enabled('caja_exigir_cajero_para_cobro')
    )
    puede_tomar_cola = _is_admin(user) or _can(user, 'tomar_cola_cobro')
    return bool(modo_cobro_exclusivo and not puede_tomar_cola)


def _is_admin(user: Any) -> bool:
    try:
        return bool(user and user.es_admin())
    except Exception:
        return False


def _can(user: Any, permission: str) -> bool:
    try:
        return bool(user and user.tiene_permiso(permission))
    except Exception:
        return False


def _can_any(user: Any, *permissions: str) -> bool:
    return any(_can(user, permission) for permission in permissions)
