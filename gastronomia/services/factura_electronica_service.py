"""Factura electronica en el cobro de caja gastronomica.

La emision en si es la del modulo `facturacion_electronica` (el mismo
`/facturacion-electronica/emitir-pos/<id_venta>` que usa el POS del sistema
padre). Aca solo vive lo propio de gastronomia: a nombre de quien sale la
factura y las validaciones que conviene hacer **antes** de cobrar, porque
despues la venta queda a nombre de ese cliente y no se puede cambiar.
"""
from __future__ import annotations

from app import db
from app.models import Configuracion
from app.models.cliente import Cliente

LIMITE_BUSQUEDA = 10


def contexto_factura_electronica_caja() -> dict:
    """Si la caja ofrece factura electronica y con que timeout espera la emision."""
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


def serializar_cliente_factura(cliente: Cliente) -> dict:
    return {
        'id_cliente': int(cliente.id_cliente),
        'nombre': cliente.nombre or '',
        'ruc_ci': cliente.ruc_ci or '',
    }


def buscar_clientes_factura(q: str) -> list[Cliente]:
    q = (q or '').strip()
    if len(q) < 2:
        return []
    return (
        Cliente.query
        .filter(
            Cliente.activo.is_(True),
            Cliente.id_cliente != 1,
            db.or_(Cliente.nombre.ilike(f'%{q}%'), Cliente.ruc_ci.ilike(f'%{q}%')),
        )
        .order_by(Cliente.nombre.asc())
        .limit(LIMITE_BUSQUEDA)
        .all()
    )


def obtener_o_crear_cliente_factura(nombre: str, ruc_ci: str) -> Cliente:
    """Alta rapida desde la caja: si el RUC/CI ya existe se reusa esa ficha."""
    nombre = (nombre or '').strip()
    ruc_ci = (ruc_ci or '').strip()
    if not ruc_ci:
        raise ValueError('Ingresa el RUC o la cedula del cliente.')
    if not nombre:
        raise ValueError('Ingresa el nombre o la razon social del cliente.')
    existente = Cliente.query.filter(Cliente.ruc_ci == ruc_ci, Cliente.id_cliente != 1).first()
    if existente:
        return existente
    cliente = Cliente(nombre=nombre[:200], ruc_ci=ruc_ci[:50], tipo='minorista', activo=True)
    db.session.add(cliente)
    db.session.commit()
    return cliente


def resolver_cliente_factura(data: dict) -> Cliente | None:
    """Cliente elegido para la factura, o None para Consumidor Final."""
    raw = data.get('id_cliente_factura')
    if raw in (None, '', 0, '0'):
        return None
    try:
        cliente_id = int(raw)
    except (TypeError, ValueError):
        raise ValueError('Cliente de la factura invalido.')
    cliente = db.session.get(Cliente, cliente_id)
    if cliente is None or not cliente.activo:
        raise ValueError('El cliente de la factura no existe o esta inactivo.')
    return cliente


def factura_electronica_solicitada(data: dict) -> bool:
    return Configuracion.parse_bool(data.get('factura_electronica'), default=False)


def validar_factura_antes_de_cobrar(cliente: Cliente | None, total) -> None:
    """Frena el cobro si la factura saldria rechazada por datos del cliente.

    Son las mismas reglas que aplica la emision, pero corridas antes de crear
    la venta: una vez cobrada, la venta queda a nombre de ese cliente.
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
