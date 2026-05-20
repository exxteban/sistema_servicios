"""
Compatibilidad de rutas legacy de ventas
"""
from importlib import import_module
from pathlib import Path

__path__ = [str(Path(__file__).with_suffix(''))]

_base_y_listado = import_module(__name__ + '.base_y_listado')
_pos_y_cola = import_module(__name__ + '.pos_y_cola')
_procesamiento = import_module(__name__ + '.procesamiento')
_post_venta = import_module(__name__ + '.post_venta')

ventas_bp = _base_y_listado.ventas_bp
_build_pos_data_from_cola_cobro = _base_y_listado._build_pos_data_from_cola_cobro
_build_venta_items_payload_from_pos_items = _base_y_listado._build_venta_items_payload_from_pos_items
_procesar_venta_payload = _procesamiento._procesar_venta_payload
_venta_existente_response = _procesamiento._venta_existente_response

__all__ = [
    "ventas_bp",
    "_build_pos_data_from_cola_cobro",
    "_build_venta_items_payload_from_pos_items",
    "_procesar_venta_payload",
    "_venta_existente_response",
]
