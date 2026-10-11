"""Factura electronica al cobrar: lo comun al POS central y a la caja gastronomica.

La emision en si es la del modulo `facturacion_electronica`
(`/facturacion-electronica/emitir-pos/<id_venta>`, despues de registrar la
venta). Aca vive si la pantalla de cobro ofrece la factura y la validacion que
conviene correr **antes** de cobrar: una vez registrada, la venta queda a
nombre de ese cliente y no se puede cambiar.
"""
from __future__ import annotations

from app import db
from app.models import Configuracion
from app.models.cliente import Cliente


def contexto_factura_electronica_pos() -> dict:
    """Si el cobro ofrece factura electronica y con que timeout espera la emision."""
    from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO
    from facturacion_electronica.services import obtener_configuracion, validar_configuracion
    from facturacion_electronica.services.proveedores.api_client import TIMEOUT_POS_SEGUNDOS
    from facturacion_electronica.services.validacion import TOPE_INNOMINADO

    activo = Configuracion.obtener_bool(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, default=False)
    return {
        'activo': bool(activo),
        'lista': bool(activo) and not validar_configuracion(obtener_configuracion()),
        'timeout_ms': TIMEOUT_POS_SEGUNDOS * 1000,
        'tope_innominado': TOPE_INNOMINADO,
    }


def validar_factura_antes_de_cobrar(cliente: Cliente | None, total) -> None:
    """Frena el cobro si la factura saldria rechazada por datos del cliente.

    Son las mismas reglas que aplica la emision, pero corridas antes de crear
    la venta. `cliente` None (o el id 1) es Consumidor Final.
    """
    from facturacion_electronica.services import obtener_configuracion
    from facturacion_electronica.services.data_builder import receptor_innominado, redondeo_sedeco
    from facturacion_electronica.services.proveedores import PROVEEDOR_API
    from facturacion_electronica.services.validacion import (
        TOPE_INNOMINADO,
        validar_cliente,
        validar_receptor_api,
    )

    error = validar_cliente(cliente)
    if not error and obtener_configuracion().proveedor == PROVEEDOR_API:
        # La API rechaza con 400 un nombre corto o un RUC con DV que no
        # corresponde; mejor decirlo antes de cobrar.
        error = validar_receptor_api(cliente)
    if error:
        raise ValueError(error)
    receptor = cliente if cliente is not None else db.session.get(Cliente, 1)
    if not receptor_innominado(receptor):
        return
    total_documento, _redondeo = redondeo_sedeco(total)
    if total_documento >= TOPE_INNOMINADO:
        raise ValueError(
            f'SIFEN no acepta facturas sin RUC ni cedula desde {TOPE_INNOMINADO:,.0f} Gs. '
            'Elegi un cliente con RUC o cedula para facturar.'.replace(',', '.')
        )
