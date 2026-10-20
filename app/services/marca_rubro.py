"""Textos de marca según el rubro de la instalación (título, barra superior y login).

En modo gastronomía las plantillas conservan su texto de siempre; esto solo decide qué
mostrar en las instalaciones de servicios. Prioridad: nombre de la empresa → texto del rubro.
"""
from __future__ import annotations

from flask import has_request_context, request

from app.services.marca_rubro_login import PANEL_LOGIN_GASTRONOMIA, panel_login_servicios


MARCA_GASTRONOMIA = {
    'es_gastronomia': True,
    'titulo': 'Sistema de Gestión Gastronómica',
    'rubro': 'Gastronomía',
    'subtitulo_login': 'Sistema de Gestión para Gastronomía',
    'panel_login': PANEL_LOGIN_GASTRONOMIA,
}

_TEXTOS_POR_DASHBOARD = {
    'peluqueria_barberia': {
        'titulo': 'Sistema de Gestión para Peluquería y Barbería',
        'rubro': 'Peluquería · Barbería',
    },
}
_TEXTOS_SERVICIOS = {
    'titulo': 'Sistema de Gestión de Servicios',
    'rubro': 'Servicios',
}


def construir_marca_rubro(*, modo: str, dashboard_id: str, nombre_empresa: str = '') -> dict:
    if modo == 'gastronomia':
        return dict(MARCA_GASTRONOMIA)
    textos = _TEXTOS_POR_DASHBOARD.get(dashboard_id, _TEXTOS_SERVICIOS)
    nombre_empresa = (nombre_empresa or '').strip()
    return {
        'es_gastronomia': False,
        'titulo': nombre_empresa or textos['titulo'],
        'rubro': textos['rubro'],
        'subtitulo_login': textos['titulo'],
        'panel_login': panel_login_servicios(dashboard_id),
    }


def obtener_marca_rubro(nombre_empresa: str = '', configuraciones: dict | None = None) -> dict:
    """Marca de la instalación actual; ante cualquier error, la de gastronomía (comportamiento de siempre).

    `configuraciones`: claves ya leídas de `Configuracion` (evita consultas extra por página).
    """
    cache = request.environ if has_request_context() else {}
    if 'app.marca_rubro' in cache:
        return cache['app.marca_rubro']
    try:
        from app.services.dashboard_negocio import CLAVE_DASHBOARD_NEGOCIO, obtener_dashboard_negocio
        from gastronomia.services.modo_operacion import (
            CLAVE_MODO_OPERACION_PRINCIPAL,
            normalizar_modo_operacion,
            obtener_modo_operacion,
        )

        configuraciones = configuraciones or {}
        modo_guardado = configuraciones.get(CLAVE_MODO_OPERACION_PRINCIPAL)
        # Sin la clave guardada, obtener_modo_operacion resuelve el modo de instalaciones viejas.
        modo = normalizar_modo_operacion(modo_guardado) if modo_guardado is not None else obtener_modo_operacion()
        dashboard_id = 'general' if modo == 'gastronomia' else obtener_dashboard_negocio(configuraciones.get(CLAVE_DASHBOARD_NEGOCIO))['id']
        marca = construir_marca_rubro(modo=modo, dashboard_id=dashboard_id, nombre_empresa=nombre_empresa)
    except Exception:
        marca = dict(MARCA_GASTRONOMIA)
    cache['app.marca_rubro'] = marca
    return marca
