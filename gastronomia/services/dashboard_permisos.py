"""Permisos que definen que tarjetas ve cada usuario en el dashboard de Gastronomia."""
from __future__ import annotations

from flask_login import current_user

from gastronomia.services.encargo_service import encargos_habilitados
from gastronomia.services.permisos import (
    PERMISO_CAJA,
    PERMISO_COCINA,
    PERMISO_DELIVERY,
    PERMISO_MENU,
    PERMISO_POS,
    PERMISO_REPORTES,
    PERMISO_SALON,
    tiene_permiso_gastronomia,
)
from gastronomia.services.produccion_service import produccion_habilitada


def permisos_dashboard(cliente_id: int | None) -> dict[str, bool]:
    return {
        'menu': tiene_permiso_gastronomia(PERMISO_MENU),
        'pos': tiene_permiso_gastronomia(PERMISO_POS),
        'salon': tiene_permiso_gastronomia(PERMISO_SALON),
        'cocina': tiene_permiso_gastronomia(PERMISO_COCINA),
        'caja': tiene_permiso_gastronomia(PERMISO_CAJA),
        'delivery': tiene_permiso_gastronomia(PERMISO_DELIVERY),
        'entregas': tiene_permiso_gastronomia(PERMISO_CAJA, PERMISO_COCINA, PERMISO_SALON),
        'reportes': tiene_permiso_gastronomia(PERMISO_REPORTES),
        # Historial de ventas del sistema (/ventas/): anular, factura, NC.
        'ventas': bool(current_user.tiene_permiso('ver_ventas')),
        # Solo con el flag de encargos encendido (por root): sin flag la tarjeta no existe.
        'encargos': tiene_permiso_gastronomia(PERMISO_POS) and encargos_habilitados(cliente_id),
        'produccion': tiene_permiso_gastronomia(PERMISO_POS, PERMISO_COCINA) and produccion_habilitada(cliente_id),
    }
