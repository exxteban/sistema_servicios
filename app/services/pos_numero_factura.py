"""¿El POS pide el número de factura? Depende de la facturación electrónica.

- **Sin facturación electrónica:** la factura es de talonario o autoimpresor y
  su número es lo único que le permite al resumen del/la contador/a armar el
  débito fiscal. Por eso el campo viene prendido.
- **Con facturación electrónica:** el número lo pone SIFEN; cargarlo a mano
  sobra y confunde. El campo queda apagado, diga lo que diga el switch.

Prendido "por defecto" no alcanza con un `default=True`: el formulario de
Configuración guarda todos los switches juntos, así que en una instalación
donde alguien guardó esa pantalla ya hay un "0" grabado sin que nadie lo haya
elegido. Se prende **una sola vez** por instalación y se deja una marca; si
después alguien lo apaga, se respeta.
"""
from app.models import Configuracion
from app.utils.modulos import _modulo_activo

CLAVE_POS_MOSTRAR_NUMERO_FACTURA = 'pos_mostrar_numero_factura'
CLAVE_PRENDIDO_SIN_FE = 'pos_mostrar_numero_factura_prendido_sin_fe'
DESC_PRENDIDO_SIN_FE = 'Marca: el campo Nro Factura del POS ya se prendió una vez por no tener facturación electrónica'


def facturacion_electronica_activa():
    from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO

    return _modulo_activo(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, False)


def _prender_una_vez():
    if Configuracion.obtener(CLAVE_PRENDIDO_SIN_FE) is not None:
        return
    Configuracion.establecer_bool(CLAVE_POS_MOSTRAR_NUMERO_FACTURA, True, commit=False)
    Configuracion.establecer_bool(CLAVE_PRENDIDO_SIN_FE, True, DESC_PRENDIDO_SIN_FE)


def pos_pide_numero_factura():
    """Lo que usa el POS, el registro vendedor y el resumen del/la contador/a."""
    if facturacion_electronica_activa():
        return False
    _prender_una_vez()
    return Configuracion.obtener_bool(CLAVE_POS_MOSTRAR_NUMERO_FACTURA, default=True)


__all__ = [
    'CLAVE_POS_MOSTRAR_NUMERO_FACTURA',
    'facturacion_electronica_activa',
    'pos_pide_numero_factura',
]
