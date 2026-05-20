"""
Compatibilidad de rutas de ventas
"""
from importlib import import_module
from pathlib import Path

__path__ = [str(Path(__file__).with_suffix(''))]

_parte1 = import_module(__name__ + '.parte1')
_parte3 = import_module(__name__ + '.parte3')
_parte4 = import_module(__name__ + '.parte4')

ventas_bp = _parte1.ventas_bp
_build_pos_data_from_cola_cobro = _parte1._build_pos_data_from_cola_cobro
_build_venta_items_payload_from_pos_items = _parte1._build_venta_items_payload_from_pos_items
_procesar_venta_payload = _parte3._procesar_venta_payload
_venta_existente_response = _parte4._venta_existente_response

__all__ = [
    'ventas_bp',
    '_build_pos_data_from_cola_cobro',
    '_build_venta_items_payload_from_pos_items',
    '_procesar_venta_payload',
    '_venta_existente_response',
]
