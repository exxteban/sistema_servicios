"""Contexto del panel de factura electronica en el detalle de una venta.

Mismo criterio que el sistema padre: sin el permiso de configuracion se muestra
el estado pero ningun boton, para no ofrecer una accion que va a terminar en
un redirect. Que se puede hacer lo decide `acciones_para_venta`.
"""
from app.models import Configuracion


def contexto_factura_electronica_venta(venta, usuario):
    from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO, MOTIVOS_NOTA_CREDITO
    from facturacion_electronica.services.acciones import acciones_para_venta

    fe = None
    if Configuracion.obtener_bool(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, default=False):
        fe = acciones_para_venta(
            venta,
            puede_operar=usuario.es_admin() or usuario.tiene_permiso('editar_configuracion'),
        )
    return {'fe': fe, 'fe_motivos_nc': MOTIVOS_NOTA_CREDITO}
