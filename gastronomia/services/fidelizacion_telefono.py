"""Ficha de cliente por telefono para los cobros de gastronomia (fase 1 del plan de BI).

Un pedido del POS o de la tienda se cobra a consumidor final, salvo que se facture a un cliente.
Con la fidelizacion activa, el celular del pedido identifica al cliente de la venta:

- Si ya hay una ficha con ese celular y esta activa, la venta queda asignada a ella.
- Si el celular es valido y no hay ninguna ficha, se crea una ficha de cliente minorista con el nombre
  del pedido, para que la compra sume. La ficha queda registrada por celular: dos cobros simultaneos
  no pueden crear dos fichas para el mismo celular.
- Si hay dos o mas fichas con ese celular, o la unica esta inactiva, no se asigna ni se crea nada:
  no se duplica ni se mezcla a nadie.
- No actua si el cajero eligio cliente para la factura, ni si se pide factura electronica.
- El consumidor final (id 1) nunca se asigna.
"""
from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Cliente
from app.services.clientes_fidelizacion import fidelizacion_config
from gastronomia.bi_models import GastronomiaBiFichaTelefono
from gastronomia.services.bi.identidad import telefono_normalizado

DIGITOS_COMPARADOS = 8
LARGO_NOMBRE = 200
MSG_CARRERA = 'Otro cobro creó la ficha de este cliente al mismo tiempo. Volvé a cobrar.'


def _columna_telefono_sin_separadores():
    return func.replace(
        func.replace(func.replace(func.replace(Cliente.telefono, ' ', ''), '-', ''), '+', ''),
        '(', '',
    )


def _clientes_con_telefono(telefono: str) -> list[Cliente]:
    """Fichas (activas o no) con ese celular normalizado. Sirve para no duplicar a nadie."""
    digitos = re.sub(r'\D', '', telefono)[-DIGITOS_COMPARADOS:]
    # El filtro SQL solo reduce candidatos; la comparacion final usa la misma normalizacion que el BI.
    candidatos = Cliente.query.filter(
        Cliente.id_cliente != 1,
        _columna_telefono_sin_separadores().like(f'%{digitos}'),
    ).all()
    return [cliente for cliente in candidatos if telefono_normalizado(cliente.telefono) == telefono]


def _ficha_registrada(cliente_id: int, telefono: str) -> Cliente | None:
    fila = GastronomiaBiFichaTelefono.query.filter_by(
        cliente_id=int(cliente_id),
        telefono_normalizado=telefono,
    ).first()
    return db.session.get(Cliente, fila.id_cliente_ficha) if fila else None


def ficha_del_celular(cliente_id: int, celular: str | None) -> Cliente | None:
    """Ficha activa que representa ese celular. No crea nada: None si no hay una sola o esta inactiva."""
    telefono = telefono_normalizado(celular)
    if not telefono:
        return None
    registrada = _ficha_registrada(cliente_id, telefono)
    if registrada is not None:
        return registrada if registrada.activo else None
    coincidentes = _clientes_con_telefono(telefono)
    if len(coincidentes) == 1 and coincidentes[0].activo:
        return coincidentes[0]
    return None


def cliente_por_telefono(cliente_id: int, celular: str | None) -> Cliente | None:
    """Ficha que la venta usaria por telefono, solo con fidelizacion activa. No crea nada."""
    if not fidelizacion_config()['activa']:
        return None
    return ficha_del_celular(cliente_id, celular)


def ficha_a_completar_ruc(cliente_id: int, celular: str | None) -> Cliente | None:
    """Ficha del celular que todavia no tiene RUC/CI: la factura la completa en vez de crear otra."""
    ficha = ficha_del_celular(cliente_id, celular)
    if ficha is None or (ficha.ruc_ci or '').strip():
        return None
    return ficha


def _nombre_para_ficha(nombre: str | None, telefono: str) -> str:
    return (nombre or '').strip()[:LARGO_NOMBRE] or telefono


def _crear_ficha(cliente_id: int, telefono: str, nombre: str | None) -> Cliente:
    cliente = Cliente(
        nombre=_nombre_para_ficha(nombre, telefono),
        telefono=telefono,
        tipo='minorista',
        activo=True,
    )
    db.session.add(cliente)
    db.session.flush()
    db.session.add(GastronomiaBiFichaTelefono(
        cliente_id=int(cliente_id),
        telefono_normalizado=telefono,
        id_cliente_ficha=int(cliente.id_cliente),
    ))
    try:
        # La clave unica por celular decide quien crea la ficha. El otro cobro vuelve a intentarlo.
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise ValueError(MSG_CARRERA)
    return cliente


def resolver_cliente_fidelizacion(
    cliente_id: int,
    celular: str | None,
    nombre: str | None,
    factura_electronica: bool,
) -> Cliente | None:
    """Cliente de la venta cuando el cajero no eligio uno para la factura. Puede crear la ficha."""
    if factura_electronica or not fidelizacion_config()['activa']:
        return None
    telefono = telefono_normalizado(celular)
    if not telefono:
        return None
    registrada = _ficha_registrada(cliente_id, telefono)
    if registrada is not None:
        return registrada if registrada.activo else None
    coincidentes = _clientes_con_telefono(telefono)
    if not coincidentes:
        return _crear_ficha(cliente_id, telefono, nombre)
    if len(coincidentes) == 1 and coincidentes[0].activo:
        return coincidentes[0]
    return None
