"""Pedidos validos y clasificacion de canal para el BI de gastronomia.

Definicion de la fase 0 (plan_bi_gastronomia.md, seccion 5):
- Cada pedido se cuenta una sola vez: es una fila de gastronomia_pedidos.
- Se excluyen los cancelados (estado 'cancelado'). No hay devoluciones parciales:
  una anulacion pasa a 'cancelado' (cambiar_estado_pedido).
- Se excluyen los importados (origen 'importado'): no tienen canal ni cliente.
- Se excluyen los encargos (es_encargo): se programan para otra fecha, asi que
  su alta no mide la demanda del dia.
- El canal de una plataforma externa viene del item (canal_precio), no del pedido.
"""
from __future__ import annotations

from app import db
from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem
from gastronomia.services.bi.identidad import pedido_identificado, telefono_invalido
from gastronomia.services.channel_price_service import CANALES_PRECIOS

CANAL_TIENDA = 'tienda_online'
CANAL_POS = 'pos'
CANAL_DESCONOCIDO = 'desconocido'

GRUPO_PROPIO = 'propio'
GRUPO_PLATAFORMA = 'plataforma'
GRUPO_DESCONOCIDO = 'desconocido'

ORIGEN_IMPORTADO = 'importado'


def clasificar_canal(origen_pedido: str | None, canales_precio=()) -> str:
    """Canal concreto: pedidosya, monchis, tienda_online, pos o desconocido."""
    plataformas = sorted(canal for canal in canales_precio if canal in CANALES_PRECIOS)
    if plataformas:
        return plataformas[0]
    origen = (origen_pedido or '').strip().lower()
    if origen in (CANAL_TIENDA, CANAL_POS):
        return origen
    return CANAL_DESCONOCIDO


def grupo_canal(canal: str) -> str:
    if canal in CANALES_PRECIOS:
        return GRUPO_PLATAFORMA
    if canal in (CANAL_TIENDA, CANAL_POS):
        return GRUPO_PROPIO
    return GRUPO_DESCONOCIDO


def criterios_base(cliente_id: int) -> list:
    """Filtros de pedido valido sin limite de fecha: historial completo del cliente."""
    return [
        GastronomiaPedido.cliente_id == int(cliente_id),
        GastronomiaPedido.estado != 'cancelado',
        GastronomiaPedido.origen_pedido != ORIGEN_IMPORTADO,
        GastronomiaPedido.es_encargo.is_(False),
    ]


def _criterios_pedidos_validos(cliente_id: int, periodo: dict) -> list:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    return [
        *criterios_base(cliente_id),
        GastronomiaPedido.fecha_creacion >= inicio,
        GastronomiaPedido.fecha_creacion < fin,
    ]


def _canales_precio_por_pedido(cliente_id: int, periodo: dict) -> dict[int, set[str]]:
    filas = (
        db.session.query(GastronomiaPedidoItem.pedido_id, GastronomiaPedidoItem.canal_precio)
        .join(GastronomiaPedido, GastronomiaPedido.id_pedido == GastronomiaPedidoItem.pedido_id)
        .filter(
            GastronomiaPedidoItem.canal_precio.isnot(None),
            *_criterios_pedidos_validos(cliente_id, periodo),
        )
        .all()
    )
    canales: dict[int, set[str]] = {}
    for pedido_id, canal in filas:
        canales.setdefault(int(pedido_id), set()).add(canal)
    return canales


def _fila(pedido, canales_precio: set[str]) -> dict:
    canal = clasificar_canal(pedido.origen_pedido, canales_precio)
    return {
        'id_pedido': int(pedido.id_pedido),
        'canal': canal,
        'grupo': grupo_canal(canal),
        'fecha_local': utc_naive_to_local(pedido.fecha_creacion).date(),
        'identificado': pedido_identificado(pedido.celular_cliente, pedido.cliente_final_id),
        'telefono_invalido': telefono_invalido(pedido.celular_cliente, pedido.cliente_final_id),
        'total': float(pedido.total or 0),
    }


def filas_pedidos_validos(cliente_id: int, periodo: dict) -> list[dict]:
    """Un dict por pedido valido del periodo, con canal, dia local, identidad y total."""
    pedidos = (
        db.session.query(
            GastronomiaPedido.id_pedido,
            GastronomiaPedido.origen_pedido,
            GastronomiaPedido.fecha_creacion,
            GastronomiaPedido.celular_cliente,
            GastronomiaPedido.cliente_final_id,
            GastronomiaPedido.total,
        )
        .filter(*_criterios_pedidos_validos(cliente_id, periodo))
        .all()
    )
    canales = _canales_precio_por_pedido(cliente_id, periodo)
    return [_fila(pedido, canales.get(int(pedido.id_pedido), set())) for pedido in pedidos]
