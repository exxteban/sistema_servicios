"""Resultados del período por fecha de cobro; la anulación se refleja al consultar."""
from collections import Counter

from flask import current_app
from sqlalchemy import func

from app import db
from app.utils.helpers import utc_bounds_for_local_dates
from gastronomia.models import GastronomiaPedidoItem as Item, GastronomiaProducto as Producto
from gastronomia.models import GastronomiaPedidoEvento as Evento
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaConfig as Config, GastronomiaSugerenciaPedido as Exposicion,
    GastronomiaSugerenciaEstadistica as Estadistica,
)
from gastronomia.services.sugerencias.aprendizaje import pagos_validos


def resumen_seguro(cliente_id, periodo):
    try:
        return resumen(cliente_id, periodo)
    except Exception:
        db.session.rollback()
        current_app.logger.exception('[gastronomia] No se pudo consultar la medición de sugerencias')
        return None


def resumen(cliente_id, periodo):
    config = Config.query.filter_by(cliente_id=cliente_id).first()
    if not (config and config.activo) and not Exposicion.query.filter_by(cliente_id=cliente_id).first():
        return None
    inicio, fin = utc_bounds_for_local_dates(periodo['desde'], periodo['hasta'])
    pagos = pagos_validos(cliente_id).subquery()
    exposiciones = (Exposicion.query.join(pagos, pagos.c.pedido_id == Exposicion.pedido_id)
                    .filter(Exposicion.cliente_id == cliente_id,
                            pagos.c.fecha_pago >= inicio, pagos.c.fecha_pago < fin).all())
    items = (db.session.query(Item).join(pagos, pagos.c.pedido_id == Item.pedido_id)
             .filter(Item.cliente_id == cliente_id, pagos.c.fecha_pago >= inicio, pagos.c.fecha_pago < fin).all())
    por_producto = {}
    for item in items:
        por_producto.setdefault((item.pedido_id, item.producto_id), []).append(item)
    guardados = dict(db.session.query(Evento.pedido_id, func.max(Evento.id_evento))
        .join(pagos, pagos.c.pedido_id == Evento.pedido_id).filter(
        Evento.cliente_id == cliente_id, Evento.tipo.in_(['pedido_creado', 'pedido_actualizado']),
        pagos.c.fecha_pago >= inicio, pagos.c.fecha_pago < fin,
    ).group_by(Evento.pedido_id))
    pedidos, renglones, destinos_vendidos, destinos_aceptados = set(), set(), set(), set()
    vendidos = Counter()
    for e in exposiciones:
        destinos = por_producto.get((e.pedido_id, e.producto_id), [])
        if not destinos:
            continue
        vendidos[(e.id_origen, e.producto_id)] += 1
        destinos_vendidos.add((e.pedido_id, e.producto_id))
        aceptados = ({i.id_item for i in destinos} & set(e.items_aceptados)
                     if e.guardado_evento_id == guardados.get(e.pedido_id) else set())
        if aceptados:
            pedidos.add(e.pedido_id)
            renglones.update(aceptados)
            destinos_aceptados.add((e.pedido_id, e.producto_id))
    nombres = dict(db.session.query(Producto.id_producto, Producto.nombre).filter_by(cliente_id=cliente_id))
    def fila(par, cantidad):
        return {'origen': nombres.get(par[0], 'Producto retirado'),
                'destino': nombres.get(par[1], 'Producto retirado'), 'cantidad': cantidad}
    nunca = (Estadistica.query.filter_by(cliente_id=cliente_id, vendidas=0)
             .filter(Estadistica.resueltas >= 10)
             .order_by(Estadistica.mostradas.desc(), Estadistica.id).limit(5).all())
    mostradas = (db.session.query(func.coalesce(func.sum(Estadistica.mostradas), 0))
                 .filter(Estadistica.cliente_id == cliente_id).scalar())
    importe = round(sum(float(i.subtotal or 0) for i in items if i.id_item in renglones), 2)
    return {
        'pedidos': len(pedidos), 'renglones': len(renglones), 'importe': importe,
        'sin_tocar': len(destinos_vendidos - destinos_aceptados),
        'mas_vendidas': [fila(par, n) for par, n in vendidos.most_common(5)],
        'nunca_vendidas': [fila((e.id_origen, e.id_destino), e.mostradas) for e in nunca],
        'mostradas': int(mostradas),
    }
