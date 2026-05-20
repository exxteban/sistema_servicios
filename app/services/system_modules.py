from __future__ import annotations

from app.models import Configuracion
from cobranzas import (
    CLAVE_COBRANZAS_ACTIVO,
    CLAVE_VENTAS_CREDITO_ACTIVO,
    DESC_COBRANZAS_ACTIVO,
    DESC_VENTAS_CREDITO_ACTIVO,
)
from control_de_empleados import CLAVE_MODULO_CONTROL_EMPLEADOS, DESC_MODULO_CONTROL_EMPLEADOS
from flujo_caja import CLAVE_MODULO_FLUJO_CAJA, DESC_MODULO_FLUJO_CAJA


CLAVE_MODULO_SERVICIO_TECNICO = 'servicio_tecnico_activo'
DESC_MODULO_SERVICIO_TECNICO = 'Activa el modulo de servicio tecnico y reparaciones'
CLAVE_MODULO_WHATSAPP = 'whatsapp_activo'
DESC_MODULO_WHATSAPP = 'Activa el modulo operativo de conversaciones de WhatsApp'
CLAVE_MODULO_CRM = 'crm_activo'
DESC_MODULO_CRM = 'Activa el modulo CRM de WhatsApp'


SYSTEM_MODULES = (
    {
        'clave': CLAVE_MODULO_FLUJO_CAJA,
        'descripcion': DESC_MODULO_FLUJO_CAJA,
        'nombre': 'flujo de caja estimado',
        'titulo': 'Flujo de caja estimado',
        'detalle': 'Muestra el acceso a tesoreria semanal y habilita sus rutas protegidas.',
        'default': True,
    },
    {
        'clave': CLAVE_MODULO_SERVICIO_TECNICO,
        'descripcion': DESC_MODULO_SERVICIO_TECNICO,
        'nombre': 'servicio tecnico',
        'titulo': 'Servicio tecnico',
        'detalle': 'Muestra el acceso de reparaciones y bloquea sus rutas internas cuando se desactiva.',
        'default': True,
    },
    {
        'clave': CLAVE_MODULO_CONTROL_EMPLEADOS,
        'descripcion': DESC_MODULO_CONTROL_EMPLEADOS,
        'nombre': 'control de empleados',
        'titulo': 'Control de empleados y salarios',
        'detalle': 'Activa el modulo aislado para empleados, sueldos, extras y descuentos.',
        'default': False,
    },
    {
        'clave': CLAVE_VENTAS_CREDITO_ACTIVO,
        'descripcion': DESC_VENTAS_CREDITO_ACTIVO,
        'nombre': 'ventas a credito',
        'titulo': 'Ventas a credito',
        'detalle': 'Habilita el medio de pago Credito Tienda en POS y la generacion de cuentas por cobrar.',
        'default': False,
    },
    {
        'clave': CLAVE_MODULO_WHATSAPP,
        'descripcion': DESC_MODULO_WHATSAPP,
        'nombre': 'whatsapp',
        'titulo': 'WhatsApp',
        'detalle': 'Muestra el panel operativo de conversaciones y bloquea sus rutas internas al desactivarlo.',
        'default': True,
    },
    {
        'clave': CLAVE_MODULO_CRM,
        'descripcion': DESC_MODULO_CRM,
        'nombre': 'crm',
        'titulo': 'CRM WhatsApp',
        'detalle': 'Muestra el acceso al CRM y bloquea sus rutas internas cuando el modulo queda oculto.',
        'default': True,
    },
    {
        'clave': CLAVE_COBRANZAS_ACTIVO,
        'descripcion': DESC_COBRANZAS_ACTIVO,
        'nombre': 'cobranzas',
        'titulo': 'Modulo de cobranzas',
        'detalle': 'Muestra el acceso operativo de cobranzas en el menu y habilita sus rutas protegidas.',
        'default': False,
    },
)

_SYSTEM_MODULES_BY_KEY = {modulo['clave']: modulo for modulo in SYSTEM_MODULES}


def iter_system_modules():
    return SYSTEM_MODULES


def get_system_module(key: str):
    return _SYSTEM_MODULES_BY_KEY.get((key or '').strip())


def system_module_enabled(key: str, default: bool = False) -> bool:
    modulo = get_system_module(key)
    resolved_default = bool(modulo['default']) if modulo is not None else bool(default)
    return Configuracion.obtener_bool(key, default=resolved_default)


def list_system_modules_with_state() -> list[dict]:
    return [
        {
            **modulo,
            'activo': system_module_enabled(modulo['clave']),
        }
        for modulo in SYSTEM_MODULES
    ]
