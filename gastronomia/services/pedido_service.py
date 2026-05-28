"""Persistencia de pedidos gastronomicos."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import case

from app import db
from gastronomia.models import (
    GastronomiaPedido,
    GastronomiaPedidoEvento,
    GastronomiaPedidoItem,
    GastronomiaPedidoItemModificador,
    GastronomiaPedidoPago,
    GastronomiaProducto,
    generar_codigo_publico_pedido,
)
from gastronomia.services.mesa_lookup import obtener_mesa_activa_por_nombre
from gastronomia.services.menu_service import parse_int
from gastronomia.services.modificadores_service import validar_selecciones_producto


TIPOS_PEDIDO = {'mesa', 'mostrador', 'retiro', 'delivery'}
ESTADOS_PEDIDO = {'abierto', 'enviado_cocina', 'preparando', 'listo', 'en_camino', 'entregado', 'cobrado', 'cancelado'}


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


def obtener_ultimo_evento_id(cliente_id: int) -> int:
    ultimo = (
        db.session.query(db.func.max(GastronomiaPedidoEvento.id_evento))
        .filter(GastronomiaPedidoEvento.cliente_id == int(cliente_id))
        .scalar()
    )
    return int(ultimo or 0)


def serializar_pedidos(pedidos: list[GastronomiaPedido]) -> list[dict]:
    if not pedidos:
        return []

    pedido_ids = [int(pedido.id_pedido) for pedido in pedidos]
    cliente_ids = {int(pedido.cliente_id) for pedido in pedidos}
    pagos = (
        GastronomiaPedidoPago.query
        .filter(
            GastronomiaPedidoPago.cliente_id.in_(cliente_ids),
            GastronomiaPedidoPago.pedido_id.in_(pedido_ids),
        )
        .all()
    )
    pagos_por_pedido = {int(pago.pedido_id): pago for pago in pagos}

    items = (
        GastronomiaPedidoItem.query
        .filter(
            GastronomiaPedidoItem.cliente_id.in_(cliente_ids),
            GastronomiaPedidoItem.pedido_id.in_(pedido_ids),
        )
        .order_by(GastronomiaPedidoItem.id_item.asc())
        .all()
    )
    item_ids = [int(item.id_item) for item in items]
    modificadores_por_item = {item_id: [] for item_id in item_ids}
    if item_ids:
        modificadores = (
            GastronomiaPedidoItemModificador.query
            .filter(
                GastronomiaPedidoItemModificador.cliente_id.in_(cliente_ids),
                GastronomiaPedidoItemModificador.item_id.in_(item_ids),
            )
            .order_by(GastronomiaPedidoItemModificador.id_modificador.asc())
            .all()
        )
        for modificador in modificadores:
            modificadores_por_item.setdefault(int(modificador.item_id), []).append(modificador.to_dict())

    items_por_pedido = {pedido_id: [] for pedido_id in pedido_ids}
    for item in items:
        item_data = {
            'id_item': item.id_item,
            'producto_id': item.producto_id,
            'nombre_producto': item.nombre_producto,
            'cantidad': int(item.cantidad or 0),
            'precio_unitario': float(item.precio_unitario or 0),
            'notas': item.notas,
            'subtotal': float(item.subtotal or 0),
            'modificadores': modificadores_por_item.get(int(item.id_item), []),
        }
        items_por_pedido.setdefault(int(item.pedido_id), []).append(item_data)

    return [
        _pedido_to_dict_prearmado(
            pedido,
            pago=pagos_por_pedido.get(int(pedido.id_pedido)),
            items=items_por_pedido.get(int(pedido.id_pedido), []),
        )
        for pedido in pedidos
    ]


def _pedido_to_dict_prearmado(pedido: GastronomiaPedido, *, pago: GastronomiaPedidoPago | None, items: list[dict]) -> dict:
    pago_data = pago.to_dict() if pago else None
    return {
        'id_pedido': pedido.id_pedido,
        'codigo_entrega': pedido.codigo_entrega,
        'cliente_id': pedido.cliente_id,
        'usuario_id': pedido.usuario_id,
        'tipo_pedido': pedido.tipo_pedido,
        'codigo_publico': pedido.codigo_publico,
        'url_seguimiento': f'/gastronomia/pedido/{pedido.codigo_publico}' if pedido.codigo_publico else None,
        'mesa': pedido.mesa,
        'referencia_entrega': pedido.referencia_entrega,
        'nombre_cliente': pedido.nombre_cliente,
        'celular_cliente': pedido.celular_cliente,
        'direccion_entrega': pedido.direccion_entrega,
        'tiempo_estimado_minutos': pedido.tiempo_estimado_minutos,
        'estado': pedido.estado,
        'notas': pedido.notas,
        'subtotal': float(pedido.subtotal or 0),
        'total': float(pedido.total or 0),
        'fecha_creacion': pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None,
        'fecha_envio_cocina': pedido.fecha_envio_cocina.isoformat() if pedido.fecha_envio_cocina else None,
        'fecha_inicio_preparacion': pedido.fecha_inicio_preparacion.isoformat() if pedido.fecha_inicio_preparacion else None,
        'fecha_listo': pedido.fecha_listo.isoformat() if pedido.fecha_listo else None,
        'fecha_entrega': pedido.fecha_entrega.isoformat() if pedido.fecha_entrega else None,
        'pagado': bool(pago),
        'estado_pago': 'pagado' if pago else 'pendiente',
        'pago': pago_data,
        'items': items,
    }


def obtener_pedido(cliente_id: int, pedido_id: int) -> GastronomiaPedido | None:
    return GastronomiaPedido.query.filter(
        GastronomiaPedido.cliente_id == int(cliente_id),
        GastronomiaPedido.id_pedido == int(pedido_id),
    ).first()


def crear_pedido(cliente_id: int, usuario_id: int, data: dict) -> GastronomiaPedido:
    pedido_data = _validar_datos_pedido(cliente_id, data)

    pedido = GastronomiaPedido(
        cliente_id=int(cliente_id),
        usuario_id=int(usuario_id),
        tipo_pedido=pedido_data['tipo_pedido'],
        codigo_publico=_codigo_publico_unico(),
        mesa=pedido_data['mesa'],
        referencia_entrega=pedido_data['referencia_entrega'],
        nombre_cliente=pedido_data['nombre_cliente'],
        celular_cliente=pedido_data['celular_cliente'],
        direccion_entrega=pedido_data['direccion_entrega'],
        tiempo_estimado_minutos=pedido_data['tiempo_estimado_minutos'],
        notas=pedido_data['notas'],
        estado='abierto',
    )
    db.session.add(pedido)
    db.session.flush()

    try:
        _reemplazar_items_pedido(cliente_id, pedido, pedido_data['items'])
    except ValueError:
        db.session.rollback()
        raise
    db.session.commit()
    registrar_evento_pedido(pedido, 'pedido_creado')
    return pedido


def actualizar_pedido_abierto(cliente_id: int, pedido_id: int, data: dict) -> GastronomiaPedido:
    pedido = obtener_pedido(cliente_id, pedido_id)
    if not pedido:
        raise ValueError('Pedido no encontrado.')
    if pedido.estado != 'abierto':
        raise ValueError('Solo se pueden editar pedidos abiertos.')
    if pedido.pago:
        raise ValueError('No se puede editar un pedido que ya fue cobrado.')

    pedido_data = _validar_datos_pedido(cliente_id, data)
    pedido.tipo_pedido = pedido_data['tipo_pedido']
    pedido.codigo_publico = pedido.codigo_publico or _codigo_publico_unico()
    pedido.mesa = pedido_data['mesa']
    pedido.referencia_entrega = pedido_data['referencia_entrega']
    pedido.nombre_cliente = pedido_data['nombre_cliente']
    pedido.celular_cliente = pedido_data['celular_cliente']
    pedido.direccion_entrega = pedido_data['direccion_entrega']
    pedido.tiempo_estimado_minutos = pedido_data['tiempo_estimado_minutos']
    pedido.notas = pedido_data['notas']
    try:
        _reemplazar_items_pedido(cliente_id, pedido, pedido_data['items'])
    except ValueError:
        db.session.rollback()
        raise
    db.session.commit()
    registrar_evento_pedido(pedido, 'pedido_actualizado')
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
    estado_anterior = pedido.estado
    if pedido.estado == 'cobrado' and estado != 'cobrado':
        raise ValueError('No se puede modificar un pedido cobrado.')
    if estado == 'en_camino' and pedido.estado not in {'listo', 'en_camino'}:
        raise ValueError('Solo se pueden despachar pedidos listos.')
    if estado == 'entregado' and pedido.estado not in {'listo', 'en_camino', 'entregado'}:
        raise ValueError('Solo se pueden entregar pedidos listos o en camino.')
    pedido.estado = estado
    if estado == 'enviado_cocina':
        pedido.fecha_envio_cocina = pedido.fecha_envio_cocina or datetime.utcnow()
    elif estado == 'preparando':
        pedido.fecha_inicio_preparacion = pedido.fecha_inicio_preparacion or datetime.utcnow()
    elif estado == 'listo':
        pedido.fecha_listo = pedido.fecha_listo or datetime.utcnow()
    elif estado in {'entregado', 'cobrado'}:
        pedido.fecha_entrega = pedido.fecha_entrega or datetime.utcnow()
    try:
        if estado == 'cancelado' and estado_anterior != 'cancelado':
            _restaurar_stock_items(pedido.items.all())
        elif estado != 'cancelado' and estado_anterior == 'cancelado':
            for item in pedido.items.all():
                _consumir_stock_producto(cliente_id, item.producto_id, int(item.cantidad or 0))
    except ValueError:
        db.session.rollback()
        raise
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


def _validar_datos_pedido(cliente_id: int, data: dict) -> dict:
    tipo = (data.get('tipo_pedido') or 'mostrador').strip().lower()
    if tipo not in TIPOS_PEDIDO:
        raise ValueError('Tipo de pedido invalido.')
    mesa = (data.get('mesa') or '').strip()[:40] or None
    if tipo == 'mesa':
        if not mesa:
            raise ValueError('La mesa es obligatoria para pedidos de mesa.')
        mesa_activa = obtener_mesa_activa_por_nombre(cliente_id, mesa)
        if not mesa_activa:
            raise ValueError('Mesa no encontrada o inactiva.')
        mesa = mesa_activa.nombre
    nombre_cliente = (data.get('nombre_cliente') or data.get('referencia_entrega') or '').strip()[:120] or None
    celular_cliente = (data.get('celular_cliente') or '').strip()[:40] or None
    direccion_entrega = (data.get('direccion_entrega') or '').strip()[:240] or None
    if tipo == 'delivery' and not celular_cliente:
        raise ValueError('El celular es obligatorio para pedidos delivery.')
    if tipo == 'delivery' and not direccion_entrega:
        raise ValueError('La direccion es obligatoria para pedidos delivery.')
    items_data = data.get('items') or []
    if not isinstance(items_data, list) or not items_data:
        raise ValueError('El pedido debe tener al menos un item.')
    return {
        'tipo_pedido': tipo,
        'mesa': mesa,
        'referencia_entrega': (data.get('referencia_entrega') or '').strip()[:80] or None,
        'nombre_cliente': nombre_cliente,
        'celular_cliente': celular_cliente,
        'direccion_entrega': direccion_entrega,
        'tiempo_estimado_minutos': _parse_estimated_minutes(data.get('tiempo_estimado_minutos')),
        'notas': (data.get('notas') or '').strip() or None,
        'items': items_data,
    }


def _codigo_publico_unico() -> str:
    for _ in range(10):
        codigo = generar_codigo_publico_pedido()
        if not GastronomiaPedido.query.filter_by(codigo_publico=codigo).first():
            return codigo
    raise ValueError('No se pudo generar el codigo publico del pedido.')


def _parse_estimated_minutes(value) -> int | None:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return None
    if minutes <= 0:
        return None
    return min(minutes, 1440)


def _reemplazar_items_pedido(cliente_id: int, pedido: GastronomiaPedido, items_data: list[dict]) -> None:
    items_anteriores = pedido.items.all()
    _restaurar_stock_items(items_anteriores)
    for item in items_anteriores:
        db.session.delete(item)
    db.session.flush()

    total = Decimal('0.00')
    for item_data in items_data:
        item = _crear_item_desde_payload(cliente_id, pedido.id_pedido, item_data)
        total += Decimal(str(item.subtotal or 0))

    pedido.subtotal = total
    pedido.total = total


def _crear_item_desde_payload(cliente_id: int, pedido_id: int, item_data: dict) -> GastronomiaPedidoItem:
    producto_id = parse_int(item_data.get('producto_id') or item_data.get('id_producto'), 0)
    cantidad = max(1, parse_int(item_data.get('cantidad'), 1))
    opciones_ids = item_data.get('opciones') or []
    validado = validar_selecciones_producto(cliente_id, producto_id, opciones_ids)
    producto = validado['producto']
    if not producto.get('visible') or not producto.get('disponible'):
        raise ValueError(f'El producto "{producto.get("nombre")}" no esta disponible.')
    _consumir_stock_producto(cliente_id, producto['id_producto'], cantidad)

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


def _consumir_stock_producto(cliente_id: int, producto_id: int, cantidad: int) -> None:
    cantidad = max(0, int(cantidad or 0))
    if cantidad <= 0:
        return

    producto = db.session.query(
        GastronomiaProducto.nombre,
        GastronomiaProducto.control_stock_venta,
    ).filter(
        GastronomiaProducto.cliente_id == int(cliente_id),
        GastronomiaProducto.id_producto == int(producto_id),
        GastronomiaProducto.activo.is_(True),
    ).first()
    if not producto or not producto.control_stock_venta:
        return

    stock_restante = GastronomiaProducto.stock_disponible - cantidad
    filas_actualizadas = (
        GastronomiaProducto.query
        .filter(
            GastronomiaProducto.cliente_id == int(cliente_id),
            GastronomiaProducto.id_producto == int(producto_id),
            GastronomiaProducto.activo.is_(True),
            GastronomiaProducto.control_stock_venta.is_(True),
            GastronomiaProducto.stock_disponible >= cantidad,
        )
        .update(
            {
                GastronomiaProducto.stock_disponible: stock_restante,
                GastronomiaProducto.disponible: case(
                    (stock_restante <= 0, False),
                    else_=GastronomiaProducto.disponible,
                ),
            },
            synchronize_session=False,
        )
    )
    if filas_actualizadas:
        return

    stock_actual = (
        db.session.query(GastronomiaProducto.stock_disponible)
        .filter(
            GastronomiaProducto.cliente_id == int(cliente_id),
            GastronomiaProducto.id_producto == int(producto_id),
            GastronomiaProducto.activo.is_(True),
            GastronomiaProducto.control_stock_venta.is_(True),
        )
        .scalar()
    )
    stock_actual = max(0, int(stock_actual or 0))
    raise ValueError(f'No hay stock suficiente de "{producto.nombre}". Quedan {stock_actual}.')


def _restaurar_stock_items(items: list[GastronomiaPedidoItem]) -> None:
    cantidades_por_producto: dict[int, int] = {}
    cliente_id = None
    for item in items:
        cliente_id = int(item.cliente_id)
        producto_id = int(item.producto_id)
        cantidades_por_producto[producto_id] = cantidades_por_producto.get(producto_id, 0) + int(item.cantidad or 0)
    if not cliente_id or not cantidades_por_producto:
        return
    productos = GastronomiaProducto.query.filter(
        GastronomiaProducto.cliente_id == cliente_id,
        GastronomiaProducto.id_producto.in_(cantidades_por_producto.keys()),
        GastronomiaProducto.activo.is_(True),
    ).all()
    for producto in productos:
        if not producto.control_stock_venta:
            continue
        producto.stock_disponible = max(0, int(producto.stock_disponible or 0)) + cantidades_por_producto[int(producto.id_producto)]
        if producto.stock_disponible > 0:
            producto.disponible = True
        db.session.add(producto)


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
