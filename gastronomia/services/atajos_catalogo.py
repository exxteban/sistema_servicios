"""Acciones de gastronomia que se pueden poner en una tecla rapida.

Son las mismas pantallas que las tarjetas del inicio de gastronomia (con sus
permisos), mas cargar menu, configurar salon y abrir caja. El nucleo de las teclas
esta en app/services/atajos_teclado.
"""
from __future__ import annotations

from typing import Any

from flask import url_for
from werkzeug.routing import BuildError

from gastronomia.services.access import cliente_id_actual_gastronomia
from gastronomia.services.dashboard_permisos import permisos_dashboard
from gastronomia.services.dashboard_preferences import DASHBOARD_CARD_DEFINITIONS

# F2 toma pedidos (como "Nueva venta" en el taller) y F4 abre la caja al empezar el turno.
ATAJOS_DEFAULT = {'F2': 'pos', 'F4': 'abrir_caja'}

_GRUPOS = {
    'operacion': 'Operación en vivo',
    'pedidos': 'Pedidos y ventas',
    'analisis': 'Análisis y producción',
}
_GRUPO_CONFIG = 'Carga y configuración'

# Titulos con acentos y mas claros para elegir en una lista; el resto usa el de la tarjeta.
_TITULOS = {
    'pos': 'POS (tomar pedido)',
    'salon': 'Salón',
    'caja': 'Caja (cobrar pedidos)',
    'produccion': 'Producción',
    'bi': 'BI Gastronomía',
}


def _url(endpoint: str, params: dict | None = None) -> str | None:
    try:
        return url_for(endpoint, **(params or {}))
    except BuildError:
        return None


def _puede(user: Any, permiso: str) -> bool:
    try:
        return bool(user.tiene_permiso(permiso))
    except Exception:
        return False


def _accion(accion_id: str, title: str, icon: str, url: str | None, group: str) -> dict | None:
    if not url:
        return None
    return {'id': accion_id, 'title': title, 'icon': icon, 'url': url, 'group': group}


def acciones_disponibles(user: Any) -> list[dict]:
    cliente_id = cliente_id_actual_gastronomia()
    if not cliente_id:
        # Sin contexto operativo las pantallas de gastronomia no abren.
        return []
    permisos = permisos_dashboard(cliente_id)
    acciones: list[dict | None] = []

    for definition in DASHBOARD_CARD_DEFINITIONS:
        if not permisos.get(definition['permission']):
            continue
        acciones.append(_accion(
            definition['id'],
            _TITULOS.get(definition['id'], definition['title']),
            definition['icon'],
            _url(definition['endpoint'], definition.get('endpoint_params')),
            _GRUPOS.get(definition['group'], ''),
        ))
        if definition['id'] == 'caja' and _puede(user, 'abrir_caja'):
            # caja.abrir ya manda al estado de caja si esta abierta: abre y cierra.
            acciones.append(_accion(
                'abrir_caja', 'Abrir / cerrar caja', 'fas fa-wallet', _url('caja.abrir'), _GRUPOS['operacion'],
            ))

    if permisos.get('menu'):
        acciones.append(_accion('menu', 'Cargar menú', 'fas fa-utensils', _url('gastronomia.menu_config'), _GRUPO_CONFIG))
    if permisos.get('salon'):
        acciones.append(_accion(
            'salon_config', 'Configurar salón', 'fas fa-chair', _url('gastronomia.salon_config'), _GRUPO_CONFIG,
        ))

    # Quien abre caja sin tener la pantalla de caja de gastronomia tambien la puede usar.
    ids = {a['id'] for a in acciones if a}
    if 'abrir_caja' not in ids and _puede(user, 'abrir_caja'):
        acciones.append(_accion(
            'abrir_caja', 'Abrir / cerrar caja', 'fas fa-wallet', _url('caja.abrir'), _GRUPOS['operacion'],
        ))

    # El POS primero en la lista: es la tecla que mas se usa.
    resultado = [a for a in acciones if a]
    resultado.sort(key=lambda a: 0 if a['id'] == 'pos' else 1)
    return resultado
