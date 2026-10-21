"""Encargos en la caja y en el cierre de turno (docs/pasteleria_fase1_diseno.md, punto B).

- Un encargo para otro dia no aparece en la lista de cobro hasta que esta
  `listo`/`entregado` o llega su fecha.
- En el cierre, los encargos futuros van a un grupo informativo propio y no
  fuerzan la confirmacion de "pedidos terminados sin cobrar".
- El informe de senas se calcula sobre la tabla de adelantos, sin tocar el arqueo.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_

from app.models import Venta
from app.utils.helpers import now_local
from gastronomia.encargo_models import (
    ADELANTO_APLICADO,
    ADELANTO_RETENIDO,
    GastronomiaPedidoAdelanto,
)
from gastronomia.models import GastronomiaPedido
from gastronomia.services.encargo_consultas import saldo_encargo


ESTADOS_ENCARGO_LISTO = ('listo', 'entregado')


def inicio_manana_local() -> datetime:
    """Medianoche de manana en hora local naive (como se guarda `fecha_programada`)."""
    hoy = now_local().replace(tzinfo=None)
    return datetime(hoy.year, hoy.month, hoy.day) + timedelta(days=1)


def filtro_visible_en_caja(manana: datetime):
    """Pedidos comunes siempre; encargos solo si estan listos o ya es su dia."""
    return or_(
        GastronomiaPedido.es_encargo.is_(False),
        GastronomiaPedido.estado.in_(ESTADOS_ENCARGO_LISTO),
        GastronomiaPedido.fecha_programada.is_(None),
        GastronomiaPedido.fecha_programada < manana,
    )


def es_encargo_futuro(pedido: GastronomiaPedido, manana: datetime) -> bool:
    return bool(pedido.es_encargo and pedido.fecha_programada and pedido.fecha_programada >= manana)


def item_encargo_pendiente(pedido: GastronomiaPedido, sena: Decimal) -> dict:
    total = Decimal(str(pedido.total or 0)).quantize(Decimal('0.01'))
    return {
        'id_pedido': pedido.id_pedido,
        'codigo_entrega': pedido.codigo_entrega,
        'estado': pedido.estado,
        'nombre_cliente': (pedido.nombre_cliente or '').strip(),
        'fecha_programada': pedido.fecha_programada.isoformat() if pedido.fecha_programada else None,
        'total': float(total),
        'sena': float(sena),
        'saldo': float(saldo_encargo(total, sena)),
    }


def resumen_encargos_pendientes(items: list[dict]) -> dict:
    return {
        'encargos_pendientes': items,
        'hay_encargos_pendientes': bool(items),
        'total_encargos_pendientes': sum(item['total'] for item in items),
        'sena_encargos_pendientes': sum(item['sena'] for item in items),
        'saldo_encargos_pendientes': sum(item['saldo'] for item in items),
    }


def informe_senas_sesion(cliente_id: int, id_sesion: int) -> dict | None:
    """Senas recibidas, devueltas, retenidas y aplicadas en una sesion de caja.

    Las retenidas van en linea propia, separadas de las ventas (el dinero ya
    entro a caja con la sena; no se factura ni se registra como venta).
    """
    base = GastronomiaPedidoAdelanto.query.filter(GastronomiaPedidoAdelanto.cliente_id == int(cliente_id))
    recibidas = base.filter(GastronomiaPedidoAdelanto.id_sesion_caja == int(id_sesion)).all()
    resueltas = base.filter(GastronomiaPedidoAdelanto.id_sesion_resolucion == int(id_sesion)).all()
    aplicadas = (
        base.join(Venta, Venta.id_venta == GastronomiaPedidoAdelanto.id_venta)
        .filter(GastronomiaPedidoAdelanto.estado == ADELANTO_APLICADO, Venta.id_sesion_caja == int(id_sesion))
        .all()
    )
    if not (recibidas or resueltas or aplicadas):
        return None

    por_metodo: dict[str, Decimal] = defaultdict(lambda: Decimal('0.00'))
    for adelanto in recibidas:
        por_metodo[adelanto.metodo_pago or 'efectivo'] += _monto(adelanto.monto)
    devueltas = [a for a in resueltas if _monto(a.monto_devuelto) > 0]
    retenidas = [a for a in resueltas if a.estado == ADELANTO_RETENIDO]
    return {
        'recibidas_total': float(sum((_monto(a.monto) for a in recibidas), Decimal('0.00'))),
        'recibidas_cantidad': len(recibidas),
        'recibidas_por_metodo': [
            {'metodo': metodo, 'monto': float(monto)} for metodo, monto in sorted(por_metodo.items())
        ],
        'devueltas_total': float(sum((_monto(a.monto_devuelto) for a in devueltas), Decimal('0.00'))),
        'devueltas_cantidad': len(devueltas),
        'retenidas_total': float(
            sum((_monto(a.monto) - _monto(a.monto_devuelto) for a in retenidas), Decimal('0.00'))
        ),
        'retenidas_cantidad': len(retenidas),
        'aplicadas_total': float(sum((_monto(a.monto) - _monto(a.monto_devuelto) for a in aplicadas), Decimal('0.00'))),
        'aplicadas_cantidad': len(aplicadas),
    }


def _monto(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(Decimal('0.01'))
