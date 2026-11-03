"""Embudo de la tienda online por plato: visitas, visitantes y pedidos web (BI-04).

- Visitas: detalle publico de cada plato de gastronomia (GastronomiaTiendaVisita).
- Visitante: hash de cliente, plato, IP y navegador. Nunca se guarda la IP.
- Pedidos web: pedidos validos con origen tienda_online. No estan vinculados a una visita:
  la relacion visitantes/pedidos es aproximada y se presenta asi.
- Un plato con pocos visitantes no se evalua: no hay evidencia para decir que no se pide.
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import current_app, has_app_context
from sqlalchemy import distinct, func

from app import db
from app.utils.helpers import today_local, utc_bounds_for_local_dates
from gastronomia.bi_models import GastronomiaTiendaVisita
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoItem, GastronomiaProducto
from gastronomia.services.bi.pedidos_validos import CANAL_TIENDA, criterios_base

DIAS_VENTANA = 30
VISITANTES_MINIMOS = 5
PEDIDOS_POR_VISITANTE_BAJO = 0.1
PLATOS_EN_LISTA = 5
PLATOS_DE_ATENCION = 3


def registrar_visita_plato(cliente_id: int, producto_id: int, visitante_hash: str) -> None:
    """Guarda la visita sin afectar la respuesta de la tienda: si falla, solo se registra el error."""
    try:
        db.session.add(GastronomiaTiendaVisita(
            cliente_id=int(cliente_id), producto_id=int(producto_id), visitante_hash=visitante_hash,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        if has_app_context():
            current_app.logger.exception('No se pudo registrar la visita a un plato de la tienda.')


def _visitas_del_periodo(cliente_id: int, inicio, fin):
    return (
        db.session.query(GastronomiaTiendaVisita.producto_id, func.count(GastronomiaTiendaVisita.id_visita),
                         func.count(distinct(GastronomiaTiendaVisita.visitante_hash)))
        .filter(
            GastronomiaTiendaVisita.cliente_id == int(cliente_id),
            GastronomiaTiendaVisita.fecha_visita >= inicio,
            GastronomiaTiendaVisita.fecha_visita < fin,
        )
        .group_by(GastronomiaTiendaVisita.producto_id)
        .all()
    )


def _pedidos_web_por_plato(cliente_id: int, inicio, fin):
    return dict(
        db.session.query(GastronomiaPedidoItem.producto_id, func.count(distinct(GastronomiaPedidoItem.pedido_id)))
        .join(GastronomiaPedido, GastronomiaPedido.id_pedido == GastronomiaPedidoItem.pedido_id)
        .filter(
            *criterios_base(cliente_id),
            GastronomiaPedido.origen_pedido == CANAL_TIENDA,
            GastronomiaPedido.fecha_creacion >= inicio,
            GastronomiaPedido.fecha_creacion < fin,
        )
        .group_by(GastronomiaPedidoItem.producto_id)
        .all()
    )


def _fila_plato(producto_id: int, nombre: str, visitas: int, visitantes: int, pedidos: int) -> dict:
    evaluable = visitantes >= VISITANTES_MINIMOS
    pedidos_por_visitante = round(pedidos / visitantes, 2) if visitantes else None
    return {
        'id_producto': producto_id,
        'nombre': nombre,
        'visitas': visitas,
        'visitantes': visitantes,
        'pedidos_web': pedidos,
        'pedidos_por_visitante': pedidos_por_visitante,
        'evaluable': evaluable,
        'poco_pedido': evaluable and pedidos_por_visitante < PEDIDOS_POR_VISITANTE_BAJO,
    }


def embudo_platos(cliente_id: int, periodo: dict) -> dict:
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    visitas = _visitas_del_periodo(cliente_id, inicio, fin)
    if not visitas:
        return {'hay_visitas': False, 'visitas': 0, 'visitantes': 0, 'pedidos_web': 0, 'platos': [], 'atencion': []}
    pedidos_web = _pedidos_web_por_plato(cliente_id, inicio, fin)
    nombres = dict(
        db.session.query(GastronomiaProducto.id_producto, GastronomiaProducto.nombre)
        .filter(GastronomiaProducto.cliente_id == int(cliente_id))
        .all()
    )
    platos = [
        _fila_plato(
            int(producto_id), nombres.get(int(producto_id), 'Plato retirado'),
            int(total_visitas), int(visitantes), int(pedidos_web.get(producto_id, 0)),
        )
        for producto_id, total_visitas, visitantes in visitas
    ]
    platos.sort(key=lambda fila: (-fila['visitantes'], fila['nombre']))
    visitantes_total = (
        db.session.query(func.count(distinct(GastronomiaTiendaVisita.visitante_hash)))
        .filter(
            GastronomiaTiendaVisita.cliente_id == int(cliente_id),
            GastronomiaTiendaVisita.fecha_visita >= inicio,
            GastronomiaTiendaVisita.fecha_visita < fin,
        )
        .scalar()
    )
    atencion = [fila for fila in platos if fila['poco_pedido']][:PLATOS_DE_ATENCION]
    return {
        'hay_visitas': True,
        'visitas': sum(int(total) for _, total, _ in visitas),
        'visitantes': int(visitantes_total or 0),
        'pedidos_web': _pedidos_web_total(cliente_id, inicio, fin),
        'platos': platos[:PLATOS_EN_LISTA],
        'atencion': atencion,
    }


def _pedidos_web_total(cliente_id: int, inicio, fin) -> int:
    return int(
        db.session.query(func.count(distinct(GastronomiaPedido.id_pedido)))
        .filter(
            *criterios_base(cliente_id),
            GastronomiaPedido.origen_pedido == CANAL_TIENDA,
            GastronomiaPedido.fecha_creacion >= inicio,
            GastronomiaPedido.fecha_creacion < fin,
        )
        .scalar() or 0
    )


def resumen_embudo(cliente_id: int, hoy: date | None = None) -> dict:
    hoy = hoy or today_local()
    periodo = {'desde': hoy - timedelta(days=DIAS_VENTANA - 1), 'hasta': hoy}
    return {
        'disponible': True,
        'dias': DIAS_VENTANA,
        'minimo_visitantes': VISITANTES_MINIMOS,
        **embudo_platos(cliente_id, periodo),
    }


def resumen_embudo_seguro(cliente_id: int, hoy: date | None = None) -> dict:
    try:
        return resumen_embudo(cliente_id, hoy)
    except Exception:
        if has_app_context():
            current_app.logger.exception('No se pudo construir el embudo de la tienda de gastronomia.')
        return {'disponible': False}
