"""
Rutas de Punto de Venta (POS) - versión legacy dividida
"""

from .base_y_listado import ventas_bp, _build_pos_data_from_cola_cobro, _build_venta_items_payload_from_pos_items
from . import base_y_listado, pos_y_cola, procesamiento, post_venta
from .procesamiento import _procesar_venta_payload, _venta_existente_response

__all__ = [
    "ventas_bp",
    "_build_pos_data_from_cola_cobro",
    "_build_venta_items_payload_from_pos_items",
    "_procesar_venta_payload",
    "_venta_existente_response",
    "base_y_listado",
    "pos_y_cola",
    "procesamiento",
    "post_venta",
]
