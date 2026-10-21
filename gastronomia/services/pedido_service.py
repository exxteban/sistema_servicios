"""Persistencia de pedidos gastronomicos."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app import db
from app.services.promociones_calculo import calculate_promotion_totals, money
from gastronomia.models import (
    GastronomiaPedido,
    GastronomiaPedidoEvento,
    GastronomiaPedidoItem,
    GastronomiaPedidoItemModificador,
    generar_codigo_publico_pedido,
)
from gastronomia.services.mesa_lookup import obtener_mesa_activa_por_nombre
from gastronomia.services.menu_service import parse_int
from gastronomia.services.modificadores_service import validar_selecciones_producto
from gastronomia.services.peso_service import linea_por_peso
from gastronomia.services.pedido_validation_utils import (
    coords_from_location_text,
    parse_estimated_minutes,
    parse_nonnegative_money,
    parse_optional_coordinate,
    parse_optional_positive_int,
)
from gastronomia.services.pedido_serializer import serializar_pedidos  # noqa: F401  (reexportado)
from gastronomia.services.pedido_stock import aplicar_stock_por_transicion, pedido_difiere_stock
from gastronomia.services.stock_service import (
    consumir_stock_item,
    restaurar_stock_items as _restaurar_stock_items,
)


TIPOS_PEDIDO = {'mesa', 'mostrador', 'retiro', 'delivery'}
ESTADOS_PEDIDO = {'abierto', 'enviado_cocina', 'preparando', 'listo', 'en_camino', 'entregado', 'cobrado', 'cancelado'}
ORIGENES_PEDIDO = {'pos', 'tienda_online'}


def listar_pedidos(
    cliente_id: int,
    *,
    estados: list[str] | None = None,
    tipo_pedido: str | None = None,
    incluir_encargos: bool = False,
) -> list[GastronomiaPedido]:
    query = GastronomiaPedido.query.filter(GastronomiaPedido.cliente_id == int(cliente_id))
    if not incluir_encargos:
        # Los encargos tienen su propio tablero; el listado operativo no los mezcla.
        query = query.filter(GastronomiaPedido.es_encargo.is_(False))
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
            db.or_(
                GastronomiaPedido.estado.in_(['enviado_cocina', 'preparando', 'listo', 'en_camino']),
                db.and_(
                    GastronomiaPedido.tipo_pedido == 'delivery',
                    GastronomiaPedido.estado == 'abierto',
                    GastronomiaPedido.origen_pedido != 'tienda_online',
                ),
            ),
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


def obtener_pedido(cliente_id: int, pedido_id: int) -> GastronomiaPedido | None:
    return GastronomiaPedido.query.filter(
        GastronomiaPedido.cliente_id == int(cliente_id),
        GastronomiaPedido.id_pedido == int(pedido_id),
    ).first()


def crear_pedido(
    cliente_id: int,
    usuario_id: int,
    data: dict,
    *,
    es_encargo: bool = False,
    fecha_programada: datetime | None = None,
) -> GastronomiaPedido:
    pedido_data = _validar_datos_pedido(cliente_id, data)
    estado_inicial = 'enviado_cocina' if pedido_data['tipo_pedido'] == 'delivery' and pedido_data['origen_pedido'] != 'tienda_online' else 'abierto'

    pedido = GastronomiaPedido(
        cliente_id=int(cliente_id),
        usuario_id=int(usuario_id),
        tipo_pedido=pedido_data['tipo_pedido'],
        origen_pedido=pedido_data['origen_pedido'],
        es_encargo=bool(es_encargo),
        fecha_programada=fecha_programada,
        codigo_publico=_codigo_publico_unico(),
        mesa=pedido_data['mesa'],
        referencia_entrega=pedido_data['referencia_entrega'],
        nombre_cliente=pedido_data['nombre_cliente'],
        celular_cliente=pedido_data['celular_cliente'],
        direccion_entrega=pedido_data['direccion_entrega'],
        cliente_final_id=pedido_data['cliente_final_id'],
        ubicacion_entrega_url=pedido_data['ubicacion_entrega_url'],
        destino_latitud=pedido_data['destino_latitud'],
        destino_longitud=pedido_data['destino_longitud'],
        tiempo_estimado_minutos=pedido_data['tiempo_estimado_minutos'],
        costo_envio=pedido_data['costo_envio'],
        notas=pedido_data['notas'],
        estado=estado_inicial,
        fecha_envio_cocina=datetime.utcnow() if estado_inicial == 'enviado_cocina' else None,
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


def actualizar_pedido_abierto(
    cliente_id: int,
    pedido_id: int,
    data: dict,
    *,
    fecha_programada: datetime | None = None,
    total_minimo: Decimal | None = None,
) -> GastronomiaPedido:
    pedido = obtener_pedido(cliente_id, pedido_id)
    if not pedido:
        raise ValueError('Pedido no encontrado.')
    if pedido.estado != 'abierto':
        raise ValueError('Solo se pueden editar pedidos abiertos.')
    if pedido.pago:
        raise ValueError('No se puede editar un pedido que ya fue cobrado.')

    pedido_data = _validar_datos_pedido(cliente_id, data)
    if pedido.es_encargo and pedido_data['tipo_pedido'] != 'retiro':
        raise ValueError('Los encargos solo admiten retiro en el local.')
    if fecha_programada is not None:
        pedido.fecha_programada = fecha_programada
    pedido.tipo_pedido = pedido_data['tipo_pedido']
    pedido.origen_pedido = pedido_data['origen_pedido']
    pedido.codigo_publico = pedido.codigo_publico or _codigo_publico_unico()
    pedido.mesa = pedido_data['mesa']
    pedido.referencia_entrega = pedido_data['referencia_entrega']
    pedido.nombre_cliente = pedido_data['nombre_cliente']
    pedido.celular_cliente = pedido_data['celular_cliente']
    pedido.direccion_entrega = pedido_data['direccion_entrega']
    pedido.cliente_final_id = pedido_data['cliente_final_id']
    pedido.ubicacion_entrega_url = pedido_data['ubicacion_entrega_url']
    pedido.destino_latitud = pedido_data['destino_latitud']
    pedido.destino_longitud = pedido_data['destino_longitud']
    pedido.tiempo_estimado_minutos = pedido_data['tiempo_estimado_minutos']
    pedido.costo_envio = pedido_data['costo_envio']
    pedido.notas = pedido_data['notas']
    if pedido_data['tipo_pedido'] == 'delivery':
        pedido.estado = 'enviado_cocina'
        pedido.fecha_envio_cocina = pedido.fecha_envio_cocina or datetime.utcnow()
    try:
        _reemplazar_items_pedido(cliente_id, pedido, pedido_data['items'])
        if total_minimo is not None and Decimal(str(pedido.total or 0)) <= total_minimo:
            raise ValueError('El total del encargo tiene que seguir siendo mayor que la sena cobrada.')
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


def cambiar_estado_pedido(
    cliente_id: int,
    pedido_id: int,
    estado: str,
    *,
    sena_resuelta: bool = False,
) -> GastronomiaPedido:
    pedido = obtener_pedido(cliente_id, pedido_id)
    if not pedido:
        raise ValueError('Pedido no encontrado.')
    estado = (estado or '').strip().lower()
    if estado not in ESTADOS_PEDIDO:
        raise ValueError('Estado invalido.')
    estado_anterior = pedido.estado
    if pedido.estado == 'cobrado' and estado != 'cobrado':
        raise ValueError('No se puede modificar un pedido cobrado.')
    # Cobrado solo sale del cobro en caja: marcarlo a mano dejaria el pedido sin venta.
    if estado == 'cobrado' and estado_anterior != 'cobrado' and not pedido.pago:
        raise ValueError('Para marcar el pedido como cobrado, cobralo desde la caja.')
    if estado == 'cancelado' and estado_anterior != 'cancelado' and pedido.pago:
        raise ValueError(
            'No se puede cancelar un pedido ya cobrado. '
            'Anula la venta desde reportes para revertir el cobro y restaurar el stock.'
        )
    if estado == 'cancelado' and estado_anterior != 'cancelado' and not sena_resuelta and _tiene_sena_vigente(pedido):
        raise ValueError(
            'Este encargo tiene una sena cobrada. Cancelalo desde Encargos '
            'eligiendo que hacer con la sena.'
        )
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
        aplicar_stock_por_transicion(pedido, estado_anterior, estado)
    except ValueError:
        db.session.rollback()
        raise
    db.session.commit()
    if pedido.es_encargo and estado == 'cancelado' and estado_anterior != 'cancelado':
        from gastronomia.services.encargo_foto_service import eliminar_fotos_encargo  # evita import circular

        eliminar_fotos_encargo(pedido)
    registrar_evento_pedido(pedido, f'pedido_{estado}')
    return pedido


def _tiene_sena_vigente(pedido: GastronomiaPedido) -> bool:
    return bool(pedido.es_encargo and pedido.adelantos.filter_by(estado='vigente').first())


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
    ubicacion_entrega_url = (data.get('ubicacion_entrega_url') or '').strip()[:500] or None
    destino_latitud = parse_optional_coordinate(data.get('destino_latitud'), -90, 90)
    destino_longitud = parse_optional_coordinate(data.get('destino_longitud'), -180, 180)
    if ubicacion_entrega_url and (destino_latitud is None or destino_longitud is None):
        parsed_lat, parsed_lng = coords_from_location_text(ubicacion_entrega_url)
        destino_latitud = destino_latitud if destino_latitud is not None else parsed_lat
        destino_longitud = destino_longitud if destino_longitud is not None else parsed_lng
    if tipo == 'delivery' and not celular_cliente:
        raise ValueError('El celular es obligatorio para pedidos delivery.')
    if tipo == 'delivery' and not direccion_entrega:
        raise ValueError('La direccion es obligatoria para pedidos delivery.')
    items_data = data.get('items') or []
    if not isinstance(items_data, list) or not items_data:
        raise ValueError('El pedido debe tener al menos un item.')
    if any(not isinstance(item, dict) for item in items_data):
        raise ValueError('Cada item del pedido debe ser valido.')
    from gastronomia.services.channel_price_service import validar_canal_items_pedido
    validar_canal_items_pedido(items_data)
    return {
        'tipo_pedido': tipo,
        'mesa': mesa,
        'referencia_entrega': (data.get('referencia_entrega') or '').strip()[:80] or None,
        'nombre_cliente': nombre_cliente,
        'celular_cliente': celular_cliente,
        'direccion_entrega': direccion_entrega,
        'cliente_final_id': parse_optional_positive_int(data.get('cliente_final_id')),
        'origen_pedido': _normalizar_origen_pedido(data.get('origen_pedido')),
        'ubicacion_entrega_url': ubicacion_entrega_url if tipo == 'delivery' else None,
        'destino_latitud': destino_latitud if tipo == 'delivery' else None,
        'destino_longitud': destino_longitud if tipo == 'delivery' else None,
        'tiempo_estimado_minutos': parse_estimated_minutes(data.get('tiempo_estimado_minutos')),
        'costo_envio': parse_nonnegative_money(data.get('costo_envio')) if tipo == 'delivery' else Decimal('0.00'),
        'notas': (data.get('notas') or '').strip() or None,
        'items': items_data,
    }


def _codigo_publico_unico() -> str:
    for _ in range(10):
        codigo = generar_codigo_publico_pedido()
        if not GastronomiaPedido.query.filter_by(codigo_publico=codigo).first():
            return codigo
    raise ValueError('No se pudo generar el codigo publico del pedido.')


def _normalizar_origen_pedido(value) -> str:
    origen = (value or 'pos').strip().lower()
    return origen if origen in ORIGENES_PEDIDO else 'pos'


def _reemplazar_items_pedido(cliente_id: int, pedido: GastronomiaPedido, items_data: list[dict]) -> None:
    items_anteriores = pedido.items.all()
    _restaurar_stock_items(items_anteriores)
    for item in items_anteriores:
        db.session.delete(item)
    db.session.flush()

    total = Decimal('0.00')
    diferir_stock = pedido_difiere_stock(pedido)
    for item_data in items_data:
        item = _crear_item_desde_payload(cliente_id, pedido.id_pedido, item_data, diferir_stock=diferir_stock)
        total += Decimal(str(item.subtotal or 0))

    pedido.subtotal = total
    pedido.total = total + Decimal(str(pedido.costo_envio or 0)).quantize(Decimal('0.01'))


def _crear_item_desde_payload(
    cliente_id: int,
    pedido_id: int,
    item_data: dict,
    *,
    diferir_stock: bool = False,
) -> GastronomiaPedidoItem:
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
    peso = linea_por_peso(producto, item_data, modificadores)  # None si se vende por unidad
    promotion = None if canal_precio or peso else get_active_gastronomia_product_promotion(cliente_id, producto['id_producto'])
    cantidad = peso['cantidad'] if peso else cantidad
    metrics = calculate_promotion_totals(precio_base, cantidad, promotion)
    subtotal = peso['subtotal'] if peso else money(metrics['subtotal_base'] + (modificadores * cantidad))
    precio_unitario = money(subtotal / cantidad)
    item = GastronomiaPedidoItem(
        pedido_id=pedido_id,
        cliente_id=int(cliente_id),
        producto_id=int(producto['id_producto']),
        canal_precio=canal_precio,
        nombre_producto=peso['nombre_producto'] if peso else producto['nombre'],
        cantidad=cantidad,
        precio_unitario=precio_unitario,
        precio_original=subtotal if peso else money(precio_base + modificadores),
        descuento_linea=metrics['descuento_linea'],
        id_promocion_aplicada=getattr(promotion, 'id_promocion', None),
        promocion_descripcion=metrics['descripcion'],
        cantidad_bonificada=metrics['cantidad_bonificada'],
        notas=(item_data.get('notas') or '').strip() or None,
        texto_personalizado=(item_data.get('texto_personalizado') or '').strip()[:240] or None,
        subtotal=subtotal,
        peso_kg=peso['peso_kg'] if peso else None,
        precio_por_kg=peso['precio_por_kg'] if peso else None,
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
    if not diferir_stock:
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
