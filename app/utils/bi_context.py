from __future__ import annotations

from typing import Any

from flask import current_app, g, has_request_context, url_for
from flask_login import current_user

from app.extensions import cache

BI_RESUMEN_CACHE_PREFIX = 'bi:dashboard:resumen'


def register_bi_context(app) -> None:
    @app.context_processor
    def inject_bi_context():
        user = current_user if has_request_context() else None
        resumen = getattr(g, 'inteligencia_resumen_override', None) if has_request_context() else None
        if resumen is None:
            resumen = obtener_resumen_dashboard_inteligencia_cacheado(user)

        return {
            'inteligencia_resumen': resumen,
            'inteligencia_menu_badge': int((resumen or {}).get('alertas_activas') or 0),
        }


def puede_ver_inteligencia(user: Any) -> bool:
    return _usuario_autenticado(user) and (
        _usuario_es_admin(user) or _usuario_tiene_permiso(user, 'ver_reportes')
    )


def puede_ver_productos(user: Any) -> bool:
    return _usuario_autenticado(user) and (
        _usuario_es_admin(user)
        or _usuario_tiene_permiso(user, 'ver_productos')
        or _usuario_tiene_permiso(user, 'ver_inventario')
    )


def construir_url_producto(user: Any, producto: dict | None) -> str:
    if not puede_ver_productos(user) or not isinstance(producto, dict):
        return ''

    id_producto = producto.get('id_producto')
    if id_producto and (_usuario_es_admin(user) or _usuario_tiene_permiso(user, 'editar_producto')):
        return url_for('productos.editar', id=id_producto)

    termino_busqueda = (producto.get('codigo') or '').strip() or (producto.get('nombre') or '').strip()
    if termino_busqueda:
        return url_for('productos.listar', buscar=termino_busqueda)
    return ''


def enriquecer_panel_productos_inteligencia(panel: dict | None, user: Any) -> dict | None:
    if not isinstance(panel, dict):
        return panel

    for clave_panel, clave_lista in (
        ('stock', 'riesgo_detalle'),
        ('stock', 'inmovilizado_detalle'),
        ('inventario', 'riesgo_quiebre'),
        ('inventario', 'stock_inmovilizado'),
    ):
        for producto in panel.get(clave_panel, {}).get(clave_lista, []) or []:
            if not isinstance(producto, dict):
                continue
            producto_url = construir_url_producto(user, producto)
            producto['producto_url'] = producto_url
            producto['puede_ver_producto'] = bool(producto_url)
    return panel


def obtener_resumen_dashboard_inteligencia_cacheado(user: Any) -> dict | None:
    if not puede_ver_inteligencia(user):
        return None

    cache_key = _construir_cache_key(user)
    resumen = cache.get(cache_key)
    if resumen is not None:
        return resumen

    try:
        from app.services.inteligencia import obtener_resumen_dashboard_inteligencia

        resumen = obtener_resumen_dashboard_inteligencia(
            id_cliente_tienda=getattr(user, 'id_cliente', None),
        )
    except Exception:
        current_app.logger.exception('No se pudo construir el resumen cacheado de inteligencia.')
        return None

    cache.set(cache_key, resumen, timeout=_cache_timeout())
    return resumen


def construir_resumen_dashboard_desde_panel(panel: dict | None) -> dict | None:
    if not isinstance(panel, dict):
        return None

    clientes = panel.get('clientes')
    stock = panel.get('stock')
    campanas = panel.get('campanas')
    if not isinstance(clientes, dict) or not isinstance(stock, dict) or not isinstance(campanas, dict):
        return None

    from app.services.inteligencia.panel import construir_resumen_dashboard

    return construir_resumen_dashboard(
        clientes,
        stock,
        campanas,
        int(panel.get('alertas_activas_total') or 0),
    )


def _construir_cache_key(user: Any) -> str:
    user_id = int(getattr(user, 'id_usuario', 0) or 0)
    cliente_id = int(getattr(user, 'id_cliente', 0) or 0)
    return f'{BI_RESUMEN_CACHE_PREFIX}:user:{user_id}:cliente:{cliente_id}'


def _cache_timeout() -> int:
    return int(current_app.config.get('BI_DASHBOARD_CACHE_TIMEOUT', 180) or 180)


def _usuario_autenticado(user: Any) -> bool:
    return bool(user and getattr(user, 'is_authenticated', False))


def _usuario_es_admin(user: Any) -> bool:
    try:
        return bool(user and callable(getattr(user, 'es_admin', None)) and user.es_admin())
    except Exception:
        return False


def _usuario_tiene_permiso(user: Any, permiso: str) -> bool:
    try:
        return bool(user and callable(getattr(user, 'tiene_permiso', None)) and user.tiene_permiso(permiso))
    except Exception:
        return False
