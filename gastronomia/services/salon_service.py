"""Gestion basica de mesas y salon gastronomico."""
from __future__ import annotations

from app import db
from gastronomia.models import GastronomiaMesa, GastronomiaPedido
from gastronomia.services.menu_service import parse_int
from gastronomia.services.pedido_service import obtener_pedido, registrar_evento_pedido


ESTADOS_ACTIVOS = {'abierto', 'enviado_cocina', 'preparando', 'listo', 'entregado'}


def listar_mesas(cliente_id: int, *, incluir_inactivas: bool = False) -> list[GastronomiaMesa]:
    query = GastronomiaMesa.query.filter(GastronomiaMesa.cliente_id == int(cliente_id))
    if not incluir_inactivas:
        query = query.filter(GastronomiaMesa.activo.is_(True))
    return query.order_by(GastronomiaMesa.orden.asc(), GastronomiaMesa.nombre.asc()).all()


def listar_salon(cliente_id: int) -> list[dict]:
    mesas = listar_mesas(cliente_id)
    pedidos = _pedidos_activos_por_mesa(cliente_id)
    return [_mesa_con_estado(mesa, pedidos.get(mesa.nombre.strip().lower())) for mesa in mesas]


def obtener_mesa(cliente_id: int, mesa_id: int) -> GastronomiaMesa | None:
    return GastronomiaMesa.query.filter(
        GastronomiaMesa.cliente_id == int(cliente_id),
        GastronomiaMesa.id_mesa == int(mesa_id),
    ).first()


def guardar_mesa(cliente_id: int, data: dict, *, mesa: GastronomiaMesa | None = None) -> GastronomiaMesa:
    nombre = (data.get('nombre') or '').strip()[:40]
    if not nombre:
        raise ValueError('El nombre de la mesa es obligatorio.')
    existente = GastronomiaMesa.query.filter(
        GastronomiaMesa.cliente_id == int(cliente_id),
        GastronomiaMesa.nombre == nombre,
    ).first()
    if existente and (mesa is None or existente.id_mesa != mesa.id_mesa):
        raise ValueError('Ya existe una mesa con ese nombre.')

    mesa = mesa or GastronomiaMesa(cliente_id=int(cliente_id))
    mesa.nombre = nombre
    mesa.capacidad = max(1, parse_int(data.get('capacidad'), 4))
    mesa.ubicacion = (data.get('ubicacion') or '').strip()[:80] or None
    mesa.orden = parse_int(data.get('orden'), 0)
    if 'activo' in data:
        mesa.activo = _parse_bool(data.get('activo'))
    db.session.add(mesa)
    db.session.commit()
    return mesa


def eliminar_mesa(cliente_id: int, mesa_id: int) -> bool:
    mesa = obtener_mesa(cliente_id, mesa_id)
    if not mesa:
        return False
    mesa.activo = False
    db.session.commit()
    return True


def mover_pedido_mesa(cliente_id: int, pedido_id: int, data: dict) -> GastronomiaPedido:
    pedido = obtener_pedido(cliente_id, pedido_id)
    if not pedido:
        raise ValueError('Pedido no encontrado.')
    if pedido.estado in {'cobrado', 'cancelado'}:
        raise ValueError('No se puede mover un pedido cerrado.')
    mesa_nombre = (data.get('mesa') or '').strip()[:40]
    if not mesa_nombre:
        raise ValueError('La mesa destino es obligatoria.')
    if not _mesa_activa_por_nombre(cliente_id, mesa_nombre):
        raise ValueError('Mesa destino no encontrada.')
    pedido.tipo_pedido = 'mesa'
    pedido.mesa = mesa_nombre
    db.session.commit()
    registrar_evento_pedido(pedido, 'pedido_mesa_movido')
    return pedido


def _pedidos_activos_por_mesa(cliente_id: int) -> dict[str, GastronomiaPedido]:
    pedidos = (
        GastronomiaPedido.query
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.tipo_pedido == 'mesa',
            GastronomiaPedido.mesa.isnot(None),
            GastronomiaPedido.estado.in_(ESTADOS_ACTIVOS),
        )
        .order_by(GastronomiaPedido.fecha_creacion.desc(), GastronomiaPedido.id_pedido.desc())
        .all()
    )
    por_mesa = {}
    for pedido in pedidos:
        key = (pedido.mesa or '').strip().lower()
        if key and key not in por_mesa:
            por_mesa[key] = pedido
    return por_mesa


def _mesa_con_estado(mesa: GastronomiaMesa, pedido: GastronomiaPedido | None) -> dict:
    data = mesa.to_dict()
    data['estado_salon'] = _estado_salon_para_pedido(pedido)
    data['pedido_activo'] = pedido.to_dict() if pedido else None
    return data


def _estado_salon_para_pedido(pedido: GastronomiaPedido | None) -> str:
    if not pedido:
        return 'libre'
    if pedido.estado == 'abierto':
        return 'ocupada'
    if pedido.estado in {'enviado_cocina', 'preparando'}:
        return 'esperando_cocina'
    if pedido.estado in {'listo', 'entregado'}:
        return 'listo'
    return 'libre'


def _mesa_activa_por_nombre(cliente_id: int, nombre: str) -> GastronomiaMesa | None:
    return GastronomiaMesa.query.filter(
        GastronomiaMesa.cliente_id == int(cliente_id),
        GastronomiaMesa.nombre == nombre,
        GastronomiaMesa.activo.is_(True),
    ).first()


def _parse_bool(value) -> bool:
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'si', 'sí'}
