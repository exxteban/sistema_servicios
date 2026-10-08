"""Lo que corre en cada pasada del scheduler de FE (ver app/bootstrap/runtime.py).

El envío de pendientes es lo principal. Además se renueva la tabla geográfica
del modo API cuando vence (`proveedores.api_geo`): casi siempre no hace nada,
y un fallo ahí se loguea sin frenar el envío, que es lo que no puede esperar.
"""
from flask import current_app

from facturacion_electronica.services.config_service import obtener_configuracion
from facturacion_electronica.services.envio_automatico import procesar_pendientes
from facturacion_electronica.services.proveedores import api_geo


def ejecutar():
    """Una pasada del scheduler. Devuelve el resumen del envío, para loguear."""
    resumen = procesar_pendientes()
    try:
        error = api_geo.actualizar_si_vencida(obtener_configuracion())
    except Exception:
        current_app.logger.exception('Error al renovar la tabla geográfica de la API de FE')
    else:
        if error:
            current_app.logger.warning('[facturacion_electronica] tabla geográfica sin renovar: %s', error)
    return resumen


__all__ = ['ejecutar']
