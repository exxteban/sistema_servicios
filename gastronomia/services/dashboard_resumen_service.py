"""Datos en vivo del dashboard de Gastronomia: franja del turno y badges de tarjetas."""
from __future__ import annotations

from sqlalchemy import func

from app import db
from app.services.caja_senas import sesion_caja_abierta_usuario
from app.utils.helpers import formato_moneda_local, today_local, utc_bounds_for_local_dates
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoPago
from gastronomia.services.caja_service import contar_pedidos_caja
from gastronomia.services.salon_service import resumen_ocupacion_salon
from gastronomia.services.tienda_pedido_service import contar_pedidos_tienda_pendientes


ESTADOS_EN_COCINA = ('enviado_cocina', 'preparando')


def resumen_dashboard(cliente_id: int | None, usuario, permisos: dict[str, bool]) -> dict:
    """Cada dato solo se calcula si el usuario tiene permiso sobre ese modulo."""
    resumen = {
        'caja_pendientes': 0,
        'tienda_pendientes': 0,
        'cocina_pendientes': None,
        'delivery_en_camino': None,
        'mesas_ocupadas': None,
        'mesas_total': None,
        'caja_abierta': None,
        'ventas_hoy': None,
        'ventas_hoy_formatted': None,
        'pedidos_cobrados_hoy': None,
    }
    if not cliente_id:
        return resumen
    if permisos.get('caja'):
        resumen['caja_pendientes'] = contar_pedidos_caja(cliente_id)
        resumen['caja_abierta'] = sesion_caja_abierta_usuario(usuario) is not None
    if permisos.get('pos'):
        resumen['tienda_pendientes'] = contar_pedidos_tienda_pendientes(cliente_id)
        resumen['delivery_en_camino'] = _contar_pedidos(cliente_id, ('en_camino',), tipo='delivery')
    if permisos.get('cocina'):
        resumen['cocina_pendientes'] = _contar_pedidos(cliente_id, ESTADOS_EN_COCINA)
    if permisos.get('salon'):
        resumen['mesas_ocupadas'], resumen['mesas_total'] = resumen_ocupacion_salon(cliente_id)
    if permisos.get('reportes') or permisos.get('caja'):
        total, cantidad = _cobrado_hoy(cliente_id)
        resumen['ventas_hoy'] = total
        resumen['ventas_hoy_formatted'] = formato_moneda_local(total)
        resumen['pedidos_cobrados_hoy'] = cantidad
    return resumen


def badges_dashboard(resumen: dict) -> dict[str, dict]:
    """Badge por id de tarjeta: {'text', 'tone'} con tone = alert | info | neutral."""
    badges: dict[str, dict] = {}
    _badge_conteo(badges, 'caja', resumen['caja_pendientes'], 'sin cobrar', 'alert')
    _badge_conteo(badges, 'pedidos_tienda', resumen['tienda_pendientes'], 'nuevo', 'alert', plural='nuevos')
    _badge_conteo(badges, 'cocina', resumen['cocina_pendientes'], 'en cocina', 'info')
    _badge_conteo(badges, 'delivery', resumen['delivery_en_camino'], 'en camino', 'info')
    if resumen['mesas_total']:
        badges['salon'] = {
            'text': f"{resumen['mesas_ocupadas']}/{resumen['mesas_total']} mesas",
            'tone': 'neutral',
        }
    return badges


def _badge_conteo(badges: dict, card_id: str, count: int | None, label: str, tone: str, plural: str | None = None) -> None:
    if not count:
        return
    texto = plural if plural and count != 1 else label
    badges[card_id] = {'text': f'{count} {texto}', 'tone': tone}


def _contar_pedidos(cliente_id: int, estados: tuple[str, ...], *, tipo: str | None = None) -> int:
    query = GastronomiaPedido.query.filter(
        GastronomiaPedido.cliente_id == int(cliente_id),
        GastronomiaPedido.estado.in_(estados),
    )
    if tipo:
        query = query.filter(GastronomiaPedido.tipo_pedido == tipo)
    return int(query.count())


def _cobrado_hoy(cliente_id: int) -> tuple[float, int]:
    hoy = today_local()
    inicio, fin = utc_bounds_for_local_dates(hoy, hoy)
    total, cantidad = (
        db.session.query(
            func.coalesce(func.sum(GastronomiaPedidoPago.total_cobrado), 0),
            func.count(GastronomiaPedidoPago.id_pago),
        )
        .filter(
            GastronomiaPedidoPago.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .one()
    )
    return float(total or 0), int(cantidad or 0)
