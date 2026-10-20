"""Panel izquierdo del login (icono, textos y features) según el rubro de la instalación."""
from __future__ import annotations


PANEL_LOGIN_GASTRONOMIA = {
    'icono_logo': 'fas fa-utensils',
    'iconos_flotantes': ('fas fa-burger', 'fas fa-boxes', 'fas fa-users-gear', 'fas fa-chart-pie', 'fas fa-robot'),
    'titulo': ('Tu local gastronómico,', 'en un solo lugar'),
    'descripcion': 'Gestioná pedidos, insumos, clientes y personal de tu hamburguesía, lomitería o restaurante desde un solo panel.',
    'features': (
        ('fas fa-cash-register', 'Pedidos y Caja', 'Ventas rápidas con caja integrada'),
        ('fas fa-boxes', 'Insumos y Stock', 'Control de ingredientes con alertas'),
        ('fas fa-users-gear', 'Personal y Turnos', 'Asistencia, turnos y rendimiento'),
        ('fas fa-chart-line', 'Reportes y Análisis', 'Estadísticas y gráficos al instante'),
        ('fas fa-robot', 'Asistente IA', 'Insights inteligentes de tu local'),
    ),
}

_PANEL_LOGIN_PELUQUERIA = {
    'icono_logo': 'fas fa-cut',
    'iconos_flotantes': ('fas fa-calendar-check', 'fas fa-spray-can-sparkles', 'fas fa-user-tie', 'fas fa-chart-pie', 'fas fa-robot'),
    'titulo': ('Tu peluquería o barbería,', 'en un solo lugar'),
    'descripcion': 'Gestioná turnos, clientes, profesionales y cobros de tu peluquería o barbería desde un solo panel.',
    'features': (
        ('fas fa-calendar-check', 'Agenda y Turnos', 'Reservas del día sin superposiciones'),
        ('fas fa-cash-register', 'Cobro y Caja', 'Cobro rápido con caja integrada'),
        ('fas fa-user-tie', 'Equipo y Comisiones', 'Profesionales, horarios y comisiones'),
        ('fab fa-whatsapp', 'Recordatorios', 'Avisos de turno por WhatsApp'),
        ('fas fa-chart-line', 'Reportes y Clientes', 'Historial, fidelización y estadísticas'),
    ),
}

_PANEL_LOGIN_SERVICIOS = {
    'icono_logo': 'fas fa-calendar-check',
    'iconos_flotantes': ('fas fa-calendar-days', 'fas fa-address-book', 'fas fa-users-gear', 'fas fa-chart-pie', 'fas fa-robot'),
    'titulo': ('Tu negocio de servicios,', 'en un solo lugar'),
    'descripcion': 'Gestioná agenda, clientes, personal y cobros de tu negocio desde un solo panel.',
    'features': (
        ('fas fa-calendar-check', 'Agenda y Turnos', 'Organizá las citas de tu equipo'),
        ('fas fa-cash-register', 'Cobros y Caja', 'Ventas y servicios con caja integrada'),
        ('fas fa-address-book', 'Clientes', 'Historial y seguimiento de cada cliente'),
        ('fas fa-chart-line', 'Reportes y Análisis', 'Estadísticas y gráficos al instante'),
        ('fas fa-robot', 'Asistente IA', 'Insights inteligentes de tu negocio'),
    ),
}

_PANELES_POR_DASHBOARD = {
    'peluqueria_barberia': _PANEL_LOGIN_PELUQUERIA,
}


def panel_login_servicios(dashboard_id: str) -> dict:
    return _PANELES_POR_DASHBOARD.get(dashboard_id, _PANEL_LOGIN_SERVICIOS)
