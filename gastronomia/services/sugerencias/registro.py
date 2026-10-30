"""Telemetría opcional, siempre DESPUÉS del commit del pedido y en sesión propia."""
from datetime import datetime

from flask import current_app
from sqlalchemy.orm import Session
from sqlalchemy import func

from app import db
from gastronomia.models import GastronomiaPedido as Pedido, GastronomiaPedidoItem as Item, GastronomiaProducto
from gastronomia.models import GastronomiaPedidoEvento as Evento
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaConfig as Config, GastronomiaSugerenciaPedido as Exposicion,
    GastronomiaSugerenciaEstadistica as Estadistica,
    GastronomiaSugerenciaCalculo as Estado,
)
from gastronomia.services.sugerencias import constantes as C


def entero(valor):
    return valor if type(valor) is int and 0 < valor <= 2147483647 else None


def pares(valor):
    if not isinstance(valor, list):
        return set()
    return {(p[0], p[1]) for p in valor[:C.MAX_PARES_PEDIDO]
            if isinstance(p, list) and len(p) == 2 and entero(p[0]) and entero(p[1]) and p[0] != p[1]}


def ultimo_guardado(sesion, cliente_id, pedido_id):
    return sesion.query(func.max(Evento.id_evento)).filter(
        Evento.cliente_id == cliente_id, Evento.pedido_id == pedido_id,
        Evento.tipo.in_(['pedido_creado', 'pedido_actualizado']),
    ).scalar()


def registrar_seguro(cliente_id, pedido_id, payload):
    try:
        with Session(db.engine) as sesion, sesion.begin():
            _registrar(sesion, cliente_id, pedido_id, payload)
    except Exception:
        current_app.logger.exception('[gastronomia] No se pudo registrar la medición opcional de sugerencias')


def _registrar(sesion, cliente_id, pedido_id, payload):
    pedido = sesion.query(Pedido).filter_by(cliente_id=cliente_id, id_pedido=pedido_id).with_for_update().one()
    if pedido.es_encargo or pedido.origen_pedido != 'pos':
        return
    config = sesion.query(Config).filter_by(cliente_id=cliente_id).first()
    activo = bool(config and config.activo and config.mostrar_en_pos)
    if not activo and not sesion.query(Exposicion.id).filter_by(cliente_id=cliente_id, pedido_id=pedido_id).first():
        return
    # Comparte la fila de publicación con el cálculo diario: evita perder
    # exposiciones si un worker publica mientras otro guarda un pedido.
    estado = sesion.query(Estado).filter_by(cliente_id=cliente_id).with_for_update().first()
    if estado is None:
        sesion.add(Estado(cliente_id=cliente_id))
        sesion.flush()
    anteriores = sesion.query(Exposicion).filter_by(
        cliente_id=cliente_id, pedido_id=pedido_id,
    ).with_for_update().all()
    existentes = {(e.id_origen, e.producto_id): e for e in anteriores}
    datos = payload.get('sugerencias')
    datos = datos if isinstance(datos, dict) else {}
    mostradas = pares(datos.get('mostradas')) if activo else set()
    tocadas = pares(datos.get('tocadas'))
    referencias = {n for par in mostradas for n in par}
    validos = {p[0] for p in sesion.query(GastronomiaProducto.id_producto).filter(
        GastronomiaProducto.cliente_id == cliente_id, GastronomiaProducto.id_producto.in_(referencias),
    )} if referencias else set()
    ahora = datetime.utcnow()
    nuevas = set()
    for par in sorted(mostradas):
        if par in existentes or not set(par) <= validos or len(existentes) >= C.MAX_PARES_PEDIDO:
            continue
        fila = Exposicion(cliente_id=cliente_id, pedido_id=pedido_id, id_origen=par[0],
                          producto_id=par[1], mostrada_en=ahora, items_aceptados=[])
        sesion.add(fila)
        existentes[par] = fila
        nuevas.add(par)
    if not existentes:
        return
    # El servicio guarda una fila por entrada, en el orden del payload. Nunca se usan
    # cantidades ni importes enviados por el navegador para la medición.
    items = sesion.query(Item).filter_by(cliente_id=cliente_id, pedido_id=pedido_id).order_by(Item.id_item).all()
    enviados = payload.get('items') or []
    aceptados = {par: [] for par in existentes}
    evento_id = ultimo_guardado(sesion, cliente_id, pedido_id)
    if isinstance(enviados, list) and len(enviados) == len(items):
        for enviado, item in zip(enviados, items):
            par = (entero(enviado.get('origen_sugerencia')), item.producto_id)
            if par in aceptados and entero(enviado.get('producto_id')) == item.producto_id:
                aceptados[par].append(item.id_item)
    for par, fila in existentes.items():
        tocada = bool(aceptados[par]) or par in tocadas
        primera_tocada = tocada and not fila.tocada
        fila.items_aceptados = aceptados[par]
        fila.guardado_evento_id = evento_id
        fila.tocada = bool(fila.tocada or tocada)
        estadistica = sesion.query(Estadistica).filter_by(
            cliente_id=cliente_id, id_origen=par[0], id_destino=par[1],
        ).with_for_update().first()
        if estadistica is None:
            estadistica = Estadistica(cliente_id=cliente_id, id_origen=par[0], id_destino=par[1],
                                      mostradas=0, tocadas=0)
            sesion.add(estadistica)
        if estadistica.inicio_ventana and fila.mostrada_en < estadistica.inicio_ventana:
            continue
        if par in nuevas:
            estadistica.mostradas += 1
            estadistica.ultima_vez = ahora
        if primera_tocada:
            estadistica.tocadas += 1


def restaurar_seguro(cliente_id, pedido_id, data):
    """Solo el detalle del POS necesita la atribución; listas/cocina no hacen consultas extra."""
    try:
        with Session(db.engine) as sesion:
            filas = sesion.query(Exposicion).filter_by(cliente_id=cliente_id, pedido_id=pedido_id).all()
            evento_id = ultimo_guardado(sesion, cliente_id, pedido_id)
            por_item = {item_id: (f.id_origen, f.producto_id) for f in filas
                        if f.guardado_evento_id == evento_id for item_id in f.items_aceptados}
            for item in data.get('items', []):
                par = por_item.get(item['id_item'])
                if par and par[1] == item['producto_id']:
                    item['origen_sugerencia'] = par[0]
            data['sugerencias'] = {
                'mostradas': [[f.id_origen, f.producto_id] for f in filas],
                'tocadas': [[f.id_origen, f.producto_id] for f in filas if f.tocada],
            }
    except Exception:
        current_app.logger.exception('[gastronomia] No se pudo restaurar la medición opcional de sugerencias')
    return data
