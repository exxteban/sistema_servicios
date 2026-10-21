"""Encargo por peso: ajustar una torta al peso real antes de cobrarla.

El precio por kilo queda congelado en la linea; cambia el peso, el importe y el
total del encargo. Si el total queda por debajo de la sena, el excedente se
devuelve en el momento. Ver docs/pasteleria_fase2_diseno.md, seccion 4.
"""
from __future__ import annotations

from decimal import Decimal

from app import db
from app.utils.auditoria_utils import registrar_auditoria
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem, GastronomiaPedidoItemModificador
from gastronomia.services.adelanto_service import devolver_excedente_sena, sena_vigente
from gastronomia.services.encargo_service import ESTADOS_ENCARGO_ACTIVOS, exigir_encargos_habilitados
from gastronomia.services.pedido_service import registrar_evento_pedido
from gastronomia.services.peso_service import formatear_kg, importe_por_peso, nombre_base_item, nombre_con_peso, parsear_peso


CENTAVOS = Decimal('0.01')


class DevolucionNoPermitidaError(ValueError):
    """El ajuste obligaria a devolver sena y el usuario no tiene permiso de caja."""


def ajustar_peso_encargo(
    cliente_id: int,
    usuario_id: int,
    pedido_id: int,
    item_id: int,
    peso_real,
    *,
    puede_devolver: bool = True,
) -> dict:
    exigir_encargos_habilitados(cliente_id)
    pedido = (
        GastronomiaPedido.query.populate_existing()
        .filter_by(cliente_id=int(cliente_id), id_pedido=int(pedido_id), es_encargo=True)
        .with_for_update()
        .first()
    )
    if not pedido:
        raise ValueError('Encargo no encontrado.')
    if pedido.pago or pedido.estado not in ESTADOS_ENCARGO_ACTIVOS:
        raise ValueError('Solo se ajusta el peso de encargos sin cobrar.')
    item = GastronomiaPedidoItem.query.filter_by(
        cliente_id=int(cliente_id), pedido_id=int(pedido.id_pedido), id_item=int(item_id),
    ).first()
    if not item or item.peso_kg is None:
        raise ValueError('Ese producto no se vende por peso.')

    peso = parsear_peso(peso_real)
    peso_anterior = Decimal(str(item.peso_kg))
    item.peso_kg = peso
    item.subtotal = (importe_por_peso(item.precio_por_kg, peso) + _modificadores(item)).quantize(CENTAVOS)
    item.precio_unitario = item.subtotal
    item.precio_original = item.subtotal
    item.nombre_producto = nombre_con_peso(nombre_base_item(item), peso)
    _recalcular_totales(pedido)

    devuelto = Decimal('0.00')
    excedente = sena_vigente(pedido) - Decimal(str(pedido.total or 0))
    try:
        if excedente > 0 and not puede_devolver:
            raise DevolucionNoPermitidaError('El nuevo total queda por debajo de la sena: devolverla requiere permiso de caja.')
        if excedente > 0:
            devuelto = devolver_excedente_sena(pedido, excedente, usuario_id, motivo='ajuste de peso')
        registrar_auditoria(
            accion='ajustar_peso_encargo',
            modulo='gastronomia',
            descripcion=f'Encargo #{pedido.id_pedido}: {formatear_kg(peso_anterior)} -> {formatear_kg(peso)}',
            referencia_tipo='gastronomia_pedido',
            referencia_id=int(pedido.id_pedido),
            datos_nuevos={'item': int(item.id_item), 'total': float(pedido.total), 'sena_devuelta': float(devuelto)},
            commit=False,
        )
        db.session.commit()
    except ValueError:
        db.session.rollback()
        raise
    registrar_evento_pedido(pedido, 'encargo_peso_ajustado')
    return {'pedido': pedido, 'sena_devuelta': devuelto}


def _modificadores(item: GastronomiaPedidoItem) -> Decimal:
    total = (
        db.session.query(db.func.sum(GastronomiaPedidoItemModificador.precio_delta))
        .filter(GastronomiaPedidoItemModificador.item_id == int(item.id_item))
        .scalar()
    )
    return Decimal(str(total or 0))


def _recalcular_totales(pedido: GastronomiaPedido) -> None:
    subtotal = (
        db.session.query(db.func.sum(GastronomiaPedidoItem.subtotal))
        .filter(GastronomiaPedidoItem.pedido_id == int(pedido.id_pedido))
        .scalar()
    )
    pedido.subtotal = Decimal(str(subtotal or 0)).quantize(CENTAVOS)
    pedido.total = pedido.subtotal + Decimal(str(pedido.costo_envio or 0)).quantize(CENTAVOS)
