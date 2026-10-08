"""Estado de los modulos activables (adaptador para el modulo de FE portado).

`facturacion_electronica` importa `_modulo_activo` de aca, igual que en el
sistema padre. En servicios no hay cache por request de la configuracion de UI,
asi que se lee directo de `system_module_enabled`.
"""
from __future__ import annotations

from app.services.system_modules import system_module_enabled


def _modulo_activo(clave: str, default: bool) -> bool:
    return system_module_enabled(clave, default=default)
