"""Beneficios de fidelizacion que la caja de gastronomia aplica a un cobro (fase 1 del plan de BI).

Mismos criterios que el POS de ventas: solo beneficios aplicables automaticamente, con el descuento
calculado sobre el saldo del cobro. Esta funcion solo estima el descuento para mostrarlo antes de
cobrar; el cobro vuelve a calcularlo y a validar el beneficio.
"""
from __future__ import annotations

from decimal import Decimal

from app.services.clientes_fidelizacion import calcular_descuento_beneficio_pos, obtener_beneficios_pos_cliente
from gastronomia.services.adelanto_service import sena_vigente
from gastronomia.services.fidelizacion_telefono import cliente_por_telefono


def base_del_cobro(pedido, descuento: Decimal, costo_envio: Decimal) -> Decimal:
    """Saldo del cobro sobre el que se calcula el beneficio: total menos descuentos y sena."""
    if (pedido.tipo_pedido or '').strip().lower() == 'delivery':
        total = Decimal(str(pedido.subtotal or 0)) + costo_envio
    else:
        total = Decimal(str(pedido.total or 0))
    sena = sena_vigente(pedido) if pedido.es_encargo else Decimal('0.00')
    return (total - descuento - sena).quantize(Decimal('0.01'))


def beneficios_para_cobro(cliente_id: int, pedido, descuento: Decimal, costo_envio: Decimal) -> list[dict]:
    """Beneficios aplicables del cliente de la venta, con el descuento estimado. No crea fichas."""
    ficha = cliente_por_telefono(cliente_id, pedido.celular_cliente)
    if ficha is None:
        return []
    base = base_del_cobro(pedido, descuento, costo_envio)
    items = obtener_beneficios_pos_cliente(ficha.id_cliente)['items']
    return [
        {**item, 'descuento_estimado': float(calcular_descuento_beneficio_pos(item, base))}
        for item in items
        if item['pos_aplicable']
    ]
