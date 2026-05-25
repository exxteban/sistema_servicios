"""Persistencia de pedidos gastronomicos."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app import db
from gastronomia.models import (
    GastronomiaPedido,
    GastronomiaPedidoEvento,
    GastronomiaPedidoItem,
    GastronomiaPedidoItemModificador,
)
from gastronomia.services.menu_service import parse_int
from gastronomia.services.modificadores_service import validar_selecciones_producto


TIPOS_PEDIDO = {'mesa', 'mostrador', 'retiro'}
ESTADOS_PEDIDO = {'abierto', 'enviado_cocina', 'preparando', 'listo', 'entregado', 'cobrado', 'cancelado'}


def listar_pedidos(cliente_id: int, *, estados: list[str] | None = None) -> list[GastronomiaPedido]:
    query = GastronomiaPedido.query.filter(GastronomiaPedido.cliente_id == int(cliente_id))
    estados_validos = [estado for estado in (estados or []) if estado in ESTADOS_PEDIDO]
    if estados_validos:
        query = query.filter(GastronomiaPedido.estado.in_(estados_validos))
    return query.order_by(GastronomiaPedido.fecha_creacion.desc(), GastronomiaPedido.id_pedido.desc()).all()


def listar_pedidos_cocina(cliente_id: int) -> list[GastronomiaPedido]:
    return (
        GastronomiaPedido.query
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.estado.in_(['enviado_cocina', 'preparando', 'listo']),
        )
        .order_by(GastronomiaPedido.fecha_envio_cocina.asc(), GastronomiaPedido.id_pedido.asc())
        .all()
    )


def listar_eventos_pedido(cliente_id: int, *, despues_de: int = 0, limite: int = 100) -> list[GastronomiaPedidoEvento]:
    return (
        GastronomiaPedidoEvento.query
        .filter(
            GastronomiaPedidoEvento.cliente_id == int(cliente_id),
            GastronomiaPedidoEvento.id_evento > int(despues_de or 0),
        )
        .order_by(GastronomiaPedidoEvento.id_evento.asc())
        .limit(max(1, min(200, int(limite or 100))))
        .all()
    )


def obtener_pedido(cliente_id: int, pedido_id: int) -> GastronomiaPedido | None:
    return GastronomiaPedido.query.filter(
        GastronomiaPedido.cliente_id == int(cliente_id),
        GastronomiaPedido.id_pedido == int(pedido_id),
    ).first()


def crear_pedido(cliente_id: int, usuario_id: int, data: dict) -> GastronomiaPedido:
    tipo = (data.get('tipo_pedido') or 'mostrador').strip().lower()
    if tipo not in TIPOS_PEDIDO:
        raise ValueError('Tipo de pedido invalido.')
    items_data = data.get('items') or []
    if not isinstance(items_data, list) or not items_data:
        raise ValueError('El pedido debe tener al menos un item.')

    pedido = GastronomiaPedido(
        cliente_id=int(cliente_id),
        usuario_id=int(usuario_id),
        tipo_pedido=tipo,
        mesa=(data.get('mesa') or '').strip()[:40] or None,
        notas=(data.get('notas') or '').strip() or None,
        estado='abierto',
    )
    db.session.add(pedido)
    db.session.flush()

    total = Decimal('0.00')
    for item_data in items_data:
        item = _crear_item_desde_payload(cliente_id, pedido.id_pedido, item_data)
        total += Decimal(str(item.subtotal or 0))

    pedido.subtotal = total
    pedido.total = total
    db.session.commit()
    registrar_evento_pedido(pedido, 'pedido_creado')
    return pedido


def enviar_pedido_cocina(cliente_id: int, pedido_id: int) -> GastronomiaPedido:
    pedido = obtener_pedido(cliente_id, pedido_id)
    if not pedido:
        raise ValueError('Pedido no encontrado.')
    if pedido.estado not in {'abierto', 'enviado_cocina'}:
        raise ValueError('Solo se pueden enviar pedidos abiertos a cocina.')
    pedido.estado = 'enviado_cocina'
    pedido.fecha_envio_cocina = pedido.fecha_envio_cocina or datetime.utcnow()
    db.session.commit()
    registrar_evento_pedido(pedido, 'pedido_enviado_cocina')
    return pedido


def cambiar_estado_pedido(cliente_id: int, pedido_id: int, estado: str) -> GastronomiaPedido:
    pedido = obtener_pedido(cliente_id, pedido_id)
    if not pedido:
        raise ValueError('Pedido no encontrado.')
    estado = (estado or '').strip().lower()
    if estado not in ESTADOS_PEDIDO:
        raise ValueError('Estado invalido.')
    if pedido.estado == 'cobrado' and estado != 'cobrado':
        raise ValueError('No se puede modificar un pedido cobrado.')
    pedido.estado = estado
    if estado == 'enviado_cocina':
        pedido.fecha_envio_cocina = pedido.fecha_envio_cocina or datetime.utcnow()
    elif estado == 'preparando':
        pedido.fecha_inicio_preparacion = pedido.fecha_inicio_preparacion or datetime.utcnow()
    elif estado == 'listo':
        pedido.fecha_listo = pedido.fecha_listo or datetime.utcnow()
    db.session.commit()
    registrar_evento_pedido(pedido, f'pedido_{estado}')
    return pedido


def registrar_evento_pedido(pedido: GastronomiaPedido, tipo: str) -> GastronomiaPedidoEvento:
    evento = GastronomiaPedidoEvento(
        cliente_id=int(pedido.cliente_id),
        pedido_id=int(pedido.id_pedido),
        tipo=(tipo or 'pedido_actualizado').strip()[:60],
    )
    evento.set_payload({
        'pedido': pedido.to_dict(),
        'canal': f'cliente:{pedido.cliente_id}:gastronomia',
    })
    db.session.add(evento)
    db.session.commit()
    return evento


def _crear_item_desde_payload(cliente_id: int, pedido_id: int, item_data: dict) -> GastronomiaPedidoItem:
    producto_id = parse_int(item_data.get('producto_id') or item_data.get('id_producto'), 0)
    cantidad = max(1, parse_int(item_data.get('cantidad'), 1))
    opciones_ids = item_data.get('opciones') or []
    validado = validar_selecciones_producto(cliente_id, producto_id, opciones_ids)
    producto = validado['producto']
    if not producto.get('visible') or not producto.get('disponible'):
        raise ValueError(f'El producto "{producto.get("nombre")}" no esta disponible.')

    precio_unitario = Decimal(str(validado['total']))
    subtotal = precio_unitario * Decimal(cantidad)
    item = GastronomiaPedidoItem(
        pedido_id=pedido_id,
        cliente_id=int(cliente_id),
        producto_id=int(producto['id_producto']),
        nombre_producto=producto['nombre'],
        cantidad=cantidad,
        precio_unitario=precio_unitario,
        notas=(item_data.get('notas') or '').strip() or None,
        subtotal=subtotal,
    )
    db.session.add(item)
    db.session.flush()

    for seleccion in validado['selecciones']:
        db.session.add(GastronomiaPedidoItemModificador(
            item_id=item.id_item,
            cliente_id=int(cliente_id),
            grupo_id=int(seleccion['grupo_id']),
            opcion_id=int(seleccion['id_opcion']),
            nombre_grupo=_nombre_grupo_para_opcion(cliente_id, seleccion['grupo_id']),
            nombre_opcion=seleccion['nombre'],
            tipo_grupo=_tipo_grupo_para_opcion(cliente_id, seleccion['grupo_id']),
            precio_delta=Decimal(str(seleccion['precio_delta'])),
        ))
    return item


def _grupo_snapshot(cliente_id: int, grupo_id: int) -> dict:
    from gastronomia.services.modificadores_service import obtener_grupo

    grupo = obtener_grupo(cliente_id, grupo_id)
    return {
        'nombre': grupo.nombre if grupo else 'Opcion',
        'tipo': grupo.tipo if grupo else 'extra',
    }


def _nombre_grupo_para_opcion(cliente_id: int, grupo_id: int) -> str:
    return _grupo_snapshot(cliente_id, grupo_id)['nombre']


def _tipo_grupo_para_opcion(cliente_id: int, grupo_id: int) -> str:
    return _grupo_snapshot(cliente_id, grupo_id)['tipo']
