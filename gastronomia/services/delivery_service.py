"""Gestion operativa de repartidores y hoja de ruta."""
from __future__ import annotations

from datetime import datetime

from app import db
from app.models import Usuario
from gastronomia.models import GastronomiaPedido, GastronomiaRepartidor
from gastronomia.services.pedido_service import cambiar_estado_pedido, registrar_evento_pedido


ESTADOS_RUTA = {'listo', 'en_camino'}


def listar_repartidores(cliente_id: int, *, incluir_inactivos: bool = False) -> list[GastronomiaRepartidor]:
    query = GastronomiaRepartidor.query.filter(GastronomiaRepartidor.cliente_id == int(cliente_id))
    if not incluir_inactivos:
        query = query.filter(GastronomiaRepartidor.activo.is_(True))
    return query.order_by(GastronomiaRepartidor.activo.desc(), GastronomiaRepartidor.nombre.asc()).all()


def crear_repartidor(cliente_id: int, data: dict) -> GastronomiaRepartidor:
    repartidor = GastronomiaRepartidor(cliente_id=int(cliente_id))
    _aplicar_datos_repartidor(repartidor, data)
    db.session.add(repartidor)
    db.session.commit()
    return repartidor


def actualizar_repartidor(cliente_id: int, repartidor_id: int, data: dict) -> GastronomiaRepartidor:
    repartidor = obtener_repartidor(cliente_id, repartidor_id)
    if not repartidor:
        raise ValueError('Repartidor no encontrado.')
    _aplicar_datos_repartidor(repartidor, data)
    db.session.commit()
    return repartidor


def asignar_repartidor_pedido(cliente_id: int, pedido_id: int, repartidor_id: int | None) -> GastronomiaPedido:
    pedido = _obtener_pedido_delivery(cliente_id, pedido_id)
    if pedido.estado not in {'abierto', 'enviado_cocina', 'preparando', 'listo', 'en_camino'}:
        raise ValueError('Solo se pueden asignar deliveries a pedidos activos.')

    if not repartidor_id:
        pedido.repartidor_id = None
        pedido.fecha_asignacion_delivery = None
    else:
        repartidor = obtener_repartidor(cliente_id, repartidor_id)
        if not repartidor or not repartidor.activo:
            raise ValueError('Repartidor no disponible.')
        pedido.repartidor_id = int(repartidor.id_repartidor)
        pedido.fecha_asignacion_delivery = pedido.fecha_asignacion_delivery or datetime.utcnow()

    db.session.commit()
    registrar_evento_pedido(pedido, 'pedido_repartidor_asignado')
    return pedido


def obtener_repartidor_usuario(cliente_id: int, usuario_id: int) -> GastronomiaRepartidor | None:
    return GastronomiaRepartidor.query.filter(
        GastronomiaRepartidor.cliente_id == int(cliente_id),
        GastronomiaRepartidor.usuario_id == int(usuario_id),
        GastronomiaRepartidor.activo.is_(True),
    ).first()


def listar_ruta_repartidor(cliente_id: int, usuario_id: int) -> tuple[GastronomiaRepartidor, list[GastronomiaPedido]]:
    repartidor = obtener_repartidor_usuario(cliente_id, usuario_id)
    if not repartidor:
        raise ValueError('Este usuario no esta vinculado a un repartidor activo.')
    pedidos = (
        GastronomiaPedido.query
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.tipo_pedido == 'delivery',
            GastronomiaPedido.repartidor_id == int(repartidor.id_repartidor),
            GastronomiaPedido.estado.in_(ESTADOS_RUTA),
        )
        .order_by(GastronomiaPedido.fecha_listo.asc(), GastronomiaPedido.id_pedido.asc())
        .all()
    )
    return repartidor, pedidos


def listar_ruta_operativa(cliente_id: int) -> list[GastronomiaPedido]:
    return (
        GastronomiaPedido.query
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.tipo_pedido == 'delivery',
            GastronomiaPedido.estado.in_(ESTADOS_RUTA),
        )
        .order_by(
            GastronomiaPedido.fecha_asignacion_delivery.asc(),
            GastronomiaPedido.fecha_listo.asc(),
            GastronomiaPedido.id_pedido.asc(),
        )
        .all()
    )


def marcar_pedido_ruta(cliente_id: int, usuario_id: int, pedido_id: int, estado: str) -> GastronomiaPedido:
    repartidor = obtener_repartidor_usuario(cliente_id, usuario_id)
    if not repartidor:
        raise ValueError('Este usuario no esta vinculado a un repartidor activo.')
    pedido = _obtener_pedido_delivery(cliente_id, pedido_id)
    if int(pedido.repartidor_id or 0) != int(repartidor.id_repartidor):
        raise ValueError('El pedido no esta asignado a este repartidor.')
    estado = (estado or '').strip().lower()
    if estado not in {'en_camino', 'entregado'}:
        raise ValueError('Estado de ruta invalido.')
    return cambiar_estado_pedido(cliente_id, pedido_id, estado)


def marcar_pedido_ruta_operativa(cliente_id: int, pedido_id: int, estado: str) -> GastronomiaPedido:
    _obtener_pedido_delivery(cliente_id, pedido_id)
    estado = (estado or '').strip().lower()
    if estado not in {'en_camino', 'entregado'}:
        raise ValueError('Estado de ruta invalido.')
    return cambiar_estado_pedido(cliente_id, pedido_id, estado)


def usuarios_disponibles_delivery(cliente_id: int) -> list[Usuario]:
    return (
        Usuario.query
        .filter(Usuario.id_cliente == int(cliente_id), Usuario.activo.is_(True))
        .order_by(Usuario.nombre_completo.asc(), Usuario.username.asc())
        .all()
    )


def obtener_repartidor(cliente_id: int, repartidor_id: int) -> GastronomiaRepartidor | None:
    try:
        repartidor_id = int(repartidor_id or 0)
    except (TypeError, ValueError):
        return None
    if repartidor_id <= 0:
        return None
    return GastronomiaRepartidor.query.filter(
        GastronomiaRepartidor.cliente_id == int(cliente_id),
        GastronomiaRepartidor.id_repartidor == repartidor_id,
    ).first()


def _aplicar_datos_repartidor(repartidor: GastronomiaRepartidor, data: dict) -> None:
    nombre = (data.get('nombre') or '').strip()[:120]
    if not nombre:
        raise ValueError('El nombre del repartidor es obligatorio.')

    usuario_id = _parse_optional_int(data.get('usuario_id'))
    if usuario_id:
        usuario = Usuario.query.filter_by(id_usuario=usuario_id, id_cliente=int(repartidor.cliente_id), activo=True).first()
        if not usuario:
            raise ValueError('Usuario de delivery invalido.')
        existente = GastronomiaRepartidor.query.filter(
            GastronomiaRepartidor.cliente_id == int(repartidor.cliente_id),
            GastronomiaRepartidor.usuario_id == usuario_id,
            GastronomiaRepartidor.id_repartidor != (repartidor.id_repartidor or 0),
        ).first()
        if existente:
            raise ValueError('Ese usuario ya esta vinculado a otro repartidor.')

    repartidor.usuario_id = usuario_id
    repartidor.nombre = nombre
    repartidor.celular = (data.get('celular') or '').strip()[:40] or None
    repartidor.documento = (data.get('documento') or '').strip()[:40] or None
    repartidor.vehiculo = (data.get('vehiculo') or '').strip()[:80] or None
    repartidor.patente = (data.get('patente') or '').strip()[:30] or None
    if 'activo' in data:
        repartidor.activo = bool(data.get('activo'))


def _obtener_pedido_delivery(cliente_id: int, pedido_id: int) -> GastronomiaPedido:
    pedido = GastronomiaPedido.query.filter(
        GastronomiaPedido.cliente_id == int(cliente_id),
        GastronomiaPedido.id_pedido == int(pedido_id),
        GastronomiaPedido.tipo_pedido == 'delivery',
    ).first()
    if not pedido:
        raise ValueError('Pedido delivery no encontrado.')
    return pedido


def _parse_optional_int(value) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
