"""Factura electronica en el cobro de caja gastronomica.

La emision en si es la del modulo `facturacion_electronica` (el mismo
`/facturacion-electronica/emitir-pos/<id_venta>` que usa el POS central).
Lo comun con el POS (contexto y validacion previa) esta en `app.services.fe_pos`;
aca solo vive lo propio de gastronomia: a nombre de quien sale la
factura y las validaciones que conviene hacer **antes** de cobrar, porque
despues la venta queda a nombre de ese cliente y no se puede cambiar.
"""
from __future__ import annotations

from app import db
from app.models import Configuracion
from app.models.cliente import Cliente
# Compartidas con el POS central; se reexportan con el nombre de siempre.
from app.services.fe_pos import (  # noqa: F401
    contexto_factura_electronica_pos as contexto_factura_electronica_caja,
    validar_factura_antes_de_cobrar,
)

LIMITE_BUSQUEDA = 10


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
