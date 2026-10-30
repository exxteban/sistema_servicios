"""Lectura por tramos: únicamente pedidos cobrados, sin venta anulada."""
from sqlalchemy import or_

from app import db
from app.models.venta import Venta
from gastronomia.models import GastronomiaPedido as Pedido, GastronomiaPedidoItem as Item
from gastronomia.models import GastronomiaPedidoPago as Pago
from gastronomia.services.sugerencias import constantes as C


def tickets_gastronomia(cliente_id, desde, hasta, productos_validos):
    ultimo = 0
    while True:
        consulta = (
            db.session.query(Pedido.id_pedido, Pago.fecha_pago)
            .join(Pago, (Pago.pedido_id == Pedido.id_pedido) & (Pago.cliente_id == Pedido.cliente_id))
            .outerjoin(Venta, Venta.id_venta == Pago.id_venta)
            .filter(Pedido.cliente_id == cliente_id, Pedido.id_pedido > ultimo,
                    Pago.fecha_pago >= desde, Pago.fecha_pago <= hasta,
                    or_(Pago.id_venta.is_(None), Venta.estado != 'anulada'))
        )
        if not C.INCLUIR_ENCARGOS:
            consulta = consulta.filter(Pedido.es_encargo.is_(False))
        filas = consulta.order_by(Pedido.id_pedido).limit(C.TRAMO_VENTAS).all()
        if not filas:
            return
        ultimo = filas[-1][0]
        canastas = {id_pedido: set() for id_pedido, _ in filas}
        for pedido_id, producto_id in db.session.query(Item.pedido_id, Item.producto_id).filter(
            Item.cliente_id == cliente_id, Item.pedido_id.in_(canastas),
        ):
            canastas[pedido_id].add(producto_id)
        for pedido_id, fecha in filas:
            ids = canastas[pedido_id]
            # El límite se aplica al pedido original, antes de las exclusiones.
            if len(ids) > C.MAX_RENGLONES_TICKET:
                continue
            ids = ids & productos_validos
            if ids:
                yield fecha, ids
