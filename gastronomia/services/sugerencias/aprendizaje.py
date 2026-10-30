"""Aprendizaje preparado en el cálculo diario; el POS únicamente lee los contadores."""
from datetime import datetime, timedelta

from sqlalchemy import exists, or_, case, func

from app import db
from app.models.venta import Venta
from gastronomia.models import GastronomiaPedido as Pedido, GastronomiaPedidoPago as Pago, GastronomiaPedidoItem as Item
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaPedido as Exposicion, GastronomiaSugerenciaEstadistica as Estadistica,
)
from gastronomia.services.sugerencias import constantes as C


def pagos_validos(cliente_id):
    return (db.session.query(Pago.pedido_id, Pago.fecha_pago)
            .join(Pedido, (Pedido.id_pedido == Pago.pedido_id) & (Pedido.cliente_id == Pago.cliente_id))
            .outerjoin(Venta, Venta.id_venta == Pago.id_venta)
            .filter(Pago.cliente_id == cliente_id, Pedido.es_encargo.is_(False),
                    or_(Pago.id_venta.is_(None), Venta.estado != 'anulada')))


def actualizar(cliente_id, ahora):
    """Dentro de la misma transacción/candado que publica los pares. Repetible y sin commits."""
    pagados = pagos_validos(cliente_id).subquery()
    vendido = exists().where(
        Item.cliente_id == cliente_id, Item.pedido_id == Exposicion.pedido_id,
        Item.producto_id == Exposicion.producto_id,
    )
    filas = (db.session.query(
        Exposicion.id_origen, Exposicion.producto_id,
        func.count(Exposicion.id), func.sum(case((Exposicion.tocada.is_(True), 1), else_=0)),
        func.sum(case((pagados.c.pedido_id.isnot(None), 1), else_=0)),
        func.sum(case((pagados.c.pedido_id.isnot(None) & vendido, 1), else_=0)),
        func.max(Exposicion.mostrada_en),
    ).outerjoin(pagados, pagados.c.pedido_id == Exposicion.pedido_id)
        .outerjoin(Estadistica, (Estadistica.cliente_id == cliente_id)
                   & (Estadistica.id_origen == Exposicion.id_origen)
                   & (Estadistica.id_destino == Exposicion.producto_id))
        .filter(Exposicion.cliente_id == cliente_id, Exposicion.mostrada_en <= ahora,
                or_(Estadistica.inicio_ventana.is_(None), Exposicion.mostrada_en >= Estadistica.inicio_ventana))
        .group_by(Exposicion.id_origen, Exposicion.producto_id).all())
    estadisticas = {(e.id_origen, e.id_destino): e for e in Estadistica.query.filter_by(cliente_id=cliente_id)}
    # Una anulación posterior corrige el numerador en la siguiente corrida.
    for e in estadisticas.values():
        e.mostradas = e.tocadas = e.resueltas = e.vendidas = 0
    for origen, destino, mostradas, tocadas, resueltas, vendidas, ultima in filas:
        e = estadisticas.get((origen, destino))
        if e is None:
            e = Estadistica(cliente_id=cliente_id, id_origen=origen, id_destino=destino)
            db.session.add(e)
        e.mostradas, e.tocadas, e.resueltas, e.vendidas = mostradas, int(tocadas), int(resueltas), int(vendidas)
        e.ultima_vez = ultima
        # Un pedido abierto todavía puede convertirse: no provoca fatiga ni baja la aceptación.
        if e.resueltas >= C.FATIGA_MIN_MOSTRADAS and e.vendidas / e.resueltas < C.FATIGA_TASA_MINIMA:
            e.oculto_hasta = ahora + timedelta(days=C.FATIGA_DIAS)
            e.inicio_ventana = e.oculto_hasta
            e.mostradas = e.tocadas = e.resueltas = e.vendidas = 0


def factores(cliente_id, ahora=None):
    ahora = ahora or datetime.utcnow()
    filas = Estadistica.query.filter_by(cliente_id=cliente_id).all()
    activas = [e for e in filas if not e.oculto_hasta or e.oculto_hasta <= ahora]
    promedio = (sum(e.vendidas for e in activas) + 1) / (sum(e.resueltas for e in activas) + 10)
    return {(e.id_origen, e.id_destino): {
        'oculto': bool(e.oculto_hasta and e.oculto_hasta > ahora),
        'factor': max(.5, min(1.5, ((e.vendidas + 1) / (e.resueltas + 10)) / promedio)) if e.resueltas else 1,
    } for e in filas}
