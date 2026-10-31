"""Adaptador de fidelizacion por telefono para los cobros de gastronomia (fase 1 del plan de BI).

Un pedido del POS o de la tienda se cobra a consumidor final, salvo que se facture a un cliente.
Con la fidelizacion activa, el celular del pedido identifica al cliente de la venta:

- Si ya hay una ficha con ese celular y esta activa, la venta queda asignada a ella.
- Si el celular es valido y no hay ninguna ficha, se crea una ficha de cliente minorista con el nombre
  del pedido, para que la compra sume.
- Si hay dos o mas fichas con ese celular, o la unica esta inactiva, no se asigna ni se crea nada:
  no se duplica ni se mezcla a nadie.
- No actua si el cajero eligio cliente para la factura, ni si se pide factura electronica.
- El consumidor final (id 1) nunca se asigna.
- En gastronomia todavia no se pueden canjear beneficios: este adaptador solo acumula compras.
"""
from __future__ import annotations

import re

from sqlalchemy import func

from app import db
from app.models import Cliente
from app.services.clientes_fidelizacion import fidelizacion_config
from gastronomia.services.bi.identidad import telefono_normalizado

DIGITOS_COMPARADOS = 8
LARGO_NOMBRE = 200


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


def cliente_por_telefono(celular: str | None) -> Cliente | None:
    """Ficha activa con ese celular, solo si es la unica. Sin fidelizacion activa, None."""
    telefono = telefono_normalizado(celular)
    if not telefono or not fidelizacion_config()['activa']:
        return None
    coincidentes = _clientes_con_telefono(telefono)
    if len(coincidentes) == 1 and coincidentes[0].activo:
        return coincidentes[0]
    return None


def _nombre_para_ficha(nombre: str | None, telefono: str) -> str:
    return (nombre or '').strip()[:LARGO_NOMBRE] or telefono


def resolver_cliente_fidelizacion(celular: str | None, nombre: str | None, factura_electronica: bool) -> Cliente | None:
    """Cliente de la venta cuando el cajero no eligio uno para la factura. Puede crear la ficha."""
    if factura_electronica or not fidelizacion_config()['activa']:
        return None
    telefono = telefono_normalizado(celular)
    if not telefono:
        return None
    coincidentes = _clientes_con_telefono(telefono)
    if not coincidentes:
        cliente = Cliente(
            nombre=_nombre_para_ficha(nombre, telefono),
            telefono=telefono,
            tipo='minorista',
            activo=True,
        )
        db.session.add(cliente)
        # Solo flush: la ficha queda en la misma transaccion del cobro y se revierte si el cobro falla.
        db.session.flush()
        return cliente
    if len(coincidentes) == 1 and coincidentes[0].activo:
        return coincidentes[0]
    return None
