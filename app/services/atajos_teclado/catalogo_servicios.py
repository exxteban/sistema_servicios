"""Acciones que se pueden poner en una tecla cuando la instalacion es de servicios.

Arranca de las acciones rapidas del inicio (las mismas pantallas y permisos) y suma
las del dia a dia de un negocio de servicios: nuevo turno, agenda, cargar servicio,
cliente nuevo y abrir caja.
"""
from __future__ import annotations

from typing import Any

from flask import url_for
from werkzeug.routing import BuildError

from app.services.dashboard_preferences import get_dashboard_quick_actions

# Cobrar en F2 como en el taller; nuevo turno en F4 porque es lo segundo que mas se usa.
ATAJOS_DEFAULT = {'F2': 'ventas', 'F4': 'nuevo_turno'}

_GRUPO_DIA = 'Día a día'
_GRUPO_GESTION = 'Gestión'


def _es_peluqueria() -> bool:
    try:
        from app.services.dashboard_negocio import obtener_dashboard_negocio_actual
        return obtener_dashboard_negocio_actual().get('id') == 'peluqueria_barberia'
    except Exception:
        return False


def _puede(user: Any, permiso: str) -> bool:
    try:
        return bool(user.tiene_permiso(permiso))
    except Exception:
        return False


def _accion(accion_id: str, title: str, icon: str, endpoint: str, group: str) -> dict | None:
    try:
        url = url_for(endpoint)
    except BuildError:
        return None
    return {'id': accion_id, 'title': title, 'icon': icon, 'url': url, 'group': group}


def _acciones_servicios(user: Any) -> list[dict | None]:
    peluqueria = _es_peluqueria()
    acciones: list[dict | None] = []
    if _puede(user, 'agenda_crear'):
        acciones.append(_accion(
            'nuevo_turno', 'Nuevo turno', 'fas fa-plus',
            'agenda.nuevo_turno_peluqueria' if peluqueria else 'agenda.nueva_actividad', _GRUPO_DIA,
        ))
    if peluqueria and _puede(user, 'agenda_acceso'):
        acciones.append(_accion(
            'agenda_dia', 'Agenda del día', 'fas fa-calendar-day', 'agenda.agenda_dia_peluqueria', _GRUPO_DIA,
        ))
    if _puede(user, 'abrir_caja'):
        # caja.abrir ya manda al estado de caja si esta abierta: sirve para abrir y para cerrar.
        acciones.append(_accion('abrir_caja', 'Abrir / cerrar caja', 'fas fa-wallet', 'caja.abrir', _GRUPO_DIA))
    acciones.append(_accion('cliente_nuevo', 'Cliente nuevo', 'fas fa-user-plus', 'clientes.nuevo', _GRUPO_DIA))
    if _puede(user, 'crear_producto'):
        acciones.append(_accion('nuevo_servicio', 'Cargar servicio', 'fas fa-concierge-bell', 'servicios.nuevo', _GRUPO_GESTION))
    if _puede(user, 'ver_inventario'):
        acciones.append(_accion('servicios_lista', 'Servicios y costos', 'fas fa-list-ul', 'servicios.listar', _GRUPO_GESTION))
    return acciones


def acciones_disponibles(user: Any) -> list[dict]:
    resultado: list[dict] = []
    vistos: set[str] = set()

    def sumar(accion: dict | None) -> None:
        if accion and accion['id'] not in vistos:
            resultado.append(accion)
            vistos.add(accion['id'])

    try:
        rapidas, _ = get_dashboard_quick_actions(user)
    except Exception:
        rapidas = []
    # La venta primero: es la que va en F2.
    for accion in rapidas:
        if accion['id'] == 'ventas':
            sumar({'id': 'ventas', 'title': accion['title'], 'icon': accion['icon'],
                   'url': accion['tab_url'], 'group': _GRUPO_DIA})
    for accion in _acciones_servicios(user):
        sumar(accion)
    for accion in rapidas:
        sumar({'id': accion['id'], 'title': accion['title'], 'icon': accion['icon'],
               'url': accion['tab_url'], 'group': _GRUPO_GESTION})
    return resultado
