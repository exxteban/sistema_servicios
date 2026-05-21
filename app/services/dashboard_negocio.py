"""Perfiles de dashboard por tipo de negocio."""
from __future__ import annotations

from app.models import Configuracion


CLAVE_DASHBOARD_NEGOCIO = 'dashboard_negocio_activo'
DASHBOARD_NEGOCIO_DEFAULT = 'general'

_DASHBOARDS_NEGOCIO = (
    {
        'id': 'general',
        'nombre': 'General',
        'titulo': 'Dashboard general',
        'descripcion': 'Resumen comercial actual para ventas, caja, inventario y operación.',
        'descripcion_corta': 'Resumen general de tu negocio',
        'template': None,
        'full_template': None,
        'icono': 'fas fa-chart-line',
    },
    {
        'id': 'servicios',
        'nombre': 'Servicios',
        'titulo': 'Dashboard de servicios',
        'descripcion': 'Base para negocios que trabajan con agenda, clientes, empleados y cobros.',
        'descripcion_corta': 'Enfoque para negocios de servicios',
        'template': None,
        'full_template': 'dashboard/servicios.html',
        'icono': 'fas fa-calendar-check',
    },
    {
        'id': 'peluqueria_barberia',
        'nombre': 'Peluquería / Barbería',
        'titulo': 'Dashboard peluquería/barbería',
        'descripcion': 'Vista enfocada en turnos del día, caja, clientes y cobro rápido.',
        'descripcion_corta': 'Agenda, atención diaria y caja para peluquería/barbería',
        'template': None,
        'full_template': 'dashboard/servicios.html',
        'icono': 'fas fa-cut',
    },
)


def listar_dashboards_negocio() -> list[dict]:
    return [dict(item) for item in _DASHBOARDS_NEGOCIO]


def normalizar_dashboard_negocio(valor: str | None) -> str:
    ids_validos = {item['id'] for item in _DASHBOARDS_NEGOCIO}
    valor_normalizado = (valor or '').strip().lower()
    return valor_normalizado if valor_normalizado in ids_validos else DASHBOARD_NEGOCIO_DEFAULT


def obtener_dashboard_negocio(valor: str | None = None) -> dict:
    dashboard_id = normalizar_dashboard_negocio(valor)
    for item in _DASHBOARDS_NEGOCIO:
        if item['id'] == dashboard_id:
            return dict(item)
    return dict(_DASHBOARDS_NEGOCIO[0])


def obtener_dashboard_negocio_actual() -> dict:
    valor = Configuracion.obtener(CLAVE_DASHBOARD_NEGOCIO, DASHBOARD_NEGOCIO_DEFAULT)
    return obtener_dashboard_negocio(valor)


def establecer_dashboard_negocio_actual(valor: str | None) -> dict:
    dashboard = obtener_dashboard_negocio(valor)
    Configuracion.establecer(
        CLAVE_DASHBOARD_NEGOCIO,
        dashboard['id'],
        'Perfil de dashboard activo segun tipo de negocio',
    )
    return dashboard
