"""Persistencia de pedidos gastronomicos."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from app import db
from app.services.promociones_calculo import calculate_promotion_totals, money
from app.utils.public_url import build_public_url
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
from gastronomia.services.stock_service import (
    alertas_stock_pedido,
    consumir_stock_item,
    restaurar_stock_items as _restaurar_stock_items,
)


TIPOS_PEDIDO = {'mesa', 'mostrador', 'retiro', 'delivery'}
ESTADOS_PEDIDO = {'abierto', 'enviado_cocina', 'preparando', 'listo', 'en_camino', 'entregado', 'cobrado', 'cancelado'}


def listar_pedidos(
    cliente_id: int,
    *,
    estados: list[str] | None = None,
    tipo_pedido: str | None = None,
) -> list[GastronomiaPedido]:
    query = GastronomiaPedido.query.filter(GastronomiaPedido.cliente_id == int(cliente_id))
    estados_validos = [estado for estado in (estados or []) if estado in ESTADOS_PEDIDO]
    if estados_validos:
        query = query.filter(GastronomiaPedido.estado.in_(estados_validos))
    tipo = (tipo_pedido or '').strip().lower()
    if tipo in TIPOS_PEDIDO:
        query = query.filter(GastronomiaPedido.tipo_pedido == tipo)
    return query.order_by(GastronomiaPedido.fecha_creacion.desc(), GastronomiaPedido.id_pedido.desc()).all()


def listar_pedidos_cocina(cliente_id: int) -> list[GastronomiaPedido]:
    return (
        GastronomiaPedido.query
        .filter(
            GastronomiaPedido.cliente_id == int(cliente_id),
            GastronomiaPedido.estado.in_(['enviado_cocina', 'preparando', 'listo', 'en_camino']),
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
            'canal_precio': item.canal_precio,
            'nombre_producto': item.nombre_producto,
            'cantidad': int(item.cantidad or 0),
            'precio_unitario': float(item.precio_unitario or 0),
            'precio_original': float(item.precio_original or 0),
            'descuento_linea': float(item.descuento_linea or 0),
            'id_promocion_aplicada': item.id_promocion_aplicada,
            'promocion_descripcion': item.promocion_descripcion,
            'cantidad_bonificada': int(item.cantidad_bonificada or 0),
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
    url_seguimiento = f'/gastronomia/pedido/{pedido.codigo_publico}' if pedido.codigo_publico else None
    return {
        'id_pedido': pedido.id_pedido,
        'codigo_entrega': pedido.codigo_entrega,
        'cliente_id': pedido.cliente_id,
        'usuario_id': pedido.usuario_id,
        'tipo_pedido': pedido.tipo_pedido,
        'codigo_publico': pedido.codigo_publico,
        'url_seguimiento': url_seguimiento,
        'url_seguimiento_publica': _url_seguimiento_publica(pedido.codigo_publico),
        'mesa': pedido.mesa,
        'referencia_entrega': pedido.referencia_entrega,
        'nombre_cliente': pedido.nombre_cliente,
        'celular_cliente': pedido.celular_cliente,
        'direccion_entrega': pedido.direccion_entrega,
        'tiempo_estimado_minutos': pedido.tiempo_estimado_minutos,
        'repartidor_id': pedido.repartidor_id,
        'repartidor': pedido.repartidor.to_dict() if pedido.repartidor else None,
        'estado': pedido.estado,
        'notas': pedido.notas,
        'subtotal': float(pedido.subtotal or 0),
        'costo_envio': float(pedido.costo_envio or 0),
        'total': float(pedido.total or 0),
        'fecha_creacion': pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None,
        'fecha_envio_cocina': pedido.fecha_envio_cocina.isoformat() if pedido.fecha_envio_cocina else None,
        'fecha_inicio_preparacion': pedido.fecha_inicio_preparacion.isoformat() if pedido.fecha_inicio_preparacion else None,
        'fecha_listo': pedido.fecha_listo.isoformat() if pedido.fecha_listo else None,
        'fecha_asignacion_delivery': pedido.fecha_asignacion_delivery.isoformat() if pedido.fecha_asignacion_delivery else None,
        'fecha_entrega': pedido.fecha_entrega.isoformat() if pedido.fecha_entrega else None,
        'pagado': bool(pago),
        'estado_pago': 'pagado' if pago else 'pendiente',
        'pago': pago_data,
        'items': items,
        'alertas_stock': alertas_stock_pedido(pedido.id_pedido),
    }


def _url_seguimiento_publica(codigo_publico: str | None) -> str | None:
    if not codigo_publico:
        return None
    return build_public_url(
        'gastronomia.seguimiento_pedido_publico',
        codigo_publico=codigo_publico,
    )


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
        costo_envio=pedido_data['costo_envio'],
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
    pedido.costo_envio = pedido_data['costo_envio']
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
                consumir_stock_item(item)
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
        'costo_envio': _parse_nonnegative_money(data.get('costo_envio')) if tipo == 'delivery' else Decimal('0.00'),
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


def _parse_nonnegative_money(value) -> Decimal:
    if value in (None, ''):
        return Decimal('0.00')
    try:
        amount = Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Monto invalido.') from exc
    if amount < 0:
        raise ValueError('El costo de envio no puede ser negativo.')
    return amount


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
    pedido.total = total + Decimal(str(pedido.costo_envio or 0)).quantize(Decimal('0.01'))


def _crear_item_desde_payload(cliente_id: int, pedido_id: int, item_data: dict) -> GastronomiaPedidoItem:
    from app.services.tienda_promociones import get_active_gastronomia_product_promotion
    from gastronomia.services.channel_price_service import normalizar_canal_precio

    producto_id = parse_int(item_data.get('producto_id') or item_data.get('id_producto'), 0)
    cantidad = max(1, parse_int(item_data.get('cantidad'), 1))
    canal_precio = normalizar_canal_precio(item_data.get('canal_precio'))
    opciones_ids = item_data.get('opciones') or []
    validado = validar_selecciones_producto(
        cliente_id,
        producto_id,
        opciones_ids,
        canal_precio=canal_precio,
    )
    producto = validado['producto']
    if not producto.get('visible') or not producto.get('disponible'):
        raise ValueError(f'El producto "{producto.get("nombre")}" no esta disponible.')
    precio_base = money(producto.get('precio_base', producto['precio']))
    modificadores = money(validado['total_modificadores'])
    promotion = None if canal_precio else get_active_gastronomia_product_promotion(cliente_id, producto['id_producto'])
    metrics = calculate_promotion_totals(precio_base, cantidad, promotion)
    subtotal = money(metrics['subtotal_base'] + (modificadores * cantidad))
    precio_unitario = money(subtotal / cantidad)
    item = GastronomiaPedidoItem(
        pedido_id=pedido_id,
        cliente_id=int(cliente_id),
        producto_id=int(producto['id_producto']),
        canal_precio=canal_precio,
        nombre_producto=producto['nombre'],
        cantidad=cantidad,
        precio_unitario=precio_unitario,
        precio_original=money(precio_base + modificadores),
        descuento_linea=metrics['descuento_linea'],
        id_promocion_aplicada=getattr(promotion, 'id_promocion', None),
        promocion_descripcion=metrics['descripcion'],
        cantidad_bonificada=metrics['cantidad_bonificada'],
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
    db.session.flush()
    consumir_stock_item(item)
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
