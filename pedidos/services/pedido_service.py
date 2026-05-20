from decimal import Decimal, InvalidOperation

from app import db
from app.models import Cliente, Producto
from pedidos.models import PedidoCliente, PedidoClienteDetalle, PedidoClienteHistorial
from pedidos.schema import (
    ESTADO_PEDIDO_BORRADOR,
    ESTADO_PEDIDO_CANCELADO,
    ESTADO_PEDIDO_PAGADO,
    ESTADO_PEDIDO_PAGO_PARCIAL,
    ESTADO_PEDIDO_PENDIENTE_SENA,
    ESTADOS_BLOQUEADOS_PEDIDO,
    ESTADOS_EDITABLES_PEDIDO,
    ESTADOS_GESTIONABLES_SPRINT_1,
)


def _to_decimal(value, default: str = '0') -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    raw = str(value).strip()
    if not raw:
        return Decimal(default)
    raw = raw.replace('Gs.', '').replace('Gs', '').replace(' ', '')
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    elif ',' in raw:
        raw = raw.replace(',', '.')
    elif raw.count('.') > 1:
        raw = raw.replace('.', '')
    elif raw.count('.') == 1:
        parte_entera, parte_decimal = raw.split('.', 1)
        if len(parte_decimal) == 3 and parte_entera.lstrip('-').isdigit() and parte_decimal.isdigit():
            raw = parte_entera + parte_decimal
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_text(value, max_len: int | None = None) -> str:
    text = ' '.join(str(value or '').strip().split())
    if max_len is not None:
        return text[:max_len]
    return text


def pedido_esta_bloqueado(pedido: PedidoCliente) -> bool:
    return (pedido.estado or '').strip() in ESTADOS_BLOQUEADOS_PEDIDO


def pedido_permite_edicion(pedido: PedidoCliente) -> bool:
    return (pedido.estado or '').strip() in ESTADOS_EDITABLES_PEDIDO


def obtener_producto_activo_bloqueado(id_producto: int) -> Producto | None:
    return (
        Producto.query
        .filter_by(id_producto=int(id_producto), activo=True)
        .with_for_update()
        .first()
    )


def obtener_stock_reservado_producto(id_producto: int, *, excluir_item_id: int | None = None) -> int:
    query = (
        db.session.query(db.func.coalesce(db.func.sum(PedidoClienteDetalle.cantidad), 0))
        .join(PedidoCliente, PedidoCliente.id_pedido == PedidoClienteDetalle.id_pedido)
        .filter(
            PedidoClienteDetalle.id_producto == int(id_producto),
            ~PedidoCliente.estado.in_(tuple(ESTADOS_BLOQUEADOS_PEDIDO)),
        )
    )
    if excluir_item_id is not None:
        query = query.filter(PedidoClienteDetalle.id_detalle_pedido != int(excluir_item_id))
    return int(query.scalar() or 0)


def calcular_stock_disponible_para_pedidos(producto: Producto, *, excluir_item_id: int | None = None) -> int:
    if producto is None or bool(getattr(producto, 'es_servicio', False)):
        return 999999
    stock_actual = int(getattr(producto, 'stock_actual', 0) or 0)
    reservado = obtener_stock_reservado_producto(int(producto.id_producto), excluir_item_id=excluir_item_id)
    return stock_actual - reservado


def _validar_reserva_stock_producto(producto: Producto, cantidad_requerida: int, *, excluir_item_id: int | None = None):
    if bool(getattr(producto, 'es_servicio', False)):
        return
    disponible = calcular_stock_disponible_para_pedidos(producto, excluir_item_id=excluir_item_id)
    if cantidad_requerida > disponible:
        raise ValueError(
            f'Stock reservado insuficiente para {producto.nombre}. Disponible para pedidos: {max(0, disponible)}.'
        )


def recalcular_totales_pedido(pedido: PedidoCliente) -> PedidoCliente:
    subtotal = Decimal('0')
    for item in pedido.detalles.all():
        item.subtotal = (_to_decimal(item.precio_unitario) * Decimal(item.cantidad or 0)).quantize(Decimal('0.01'))
        subtotal += _to_decimal(item.subtotal)
    descuento = _to_decimal(pedido.descuento_monto)
    total_pagado = Decimal('0')
    if hasattr(pedido, 'pagos'):
        for pago in pedido.pagos.filter_by(estado='activo').all():
            total_pagado += _to_decimal(pago.monto)
    else:
        total_pagado = _to_decimal(pedido.total_pagado)
    total = max(Decimal('0'), subtotal - descuento)
    saldo = max(Decimal('0'), total - total_pagado)

    pedido.subtotal = subtotal.quantize(Decimal('0.01'))
    pedido.total = total.quantize(Decimal('0.01'))
    pedido.total_pagado = total_pagado.quantize(Decimal('0.01'))
    pedido.saldo_pendiente = saldo.quantize(Decimal('0.01'))
    return pedido


def _resolver_estado_reapertura(pedido: PedidoCliente) -> str:
    total = _to_decimal(pedido.total)
    total_pagado = _to_decimal(pedido.total_pagado)
    saldo = _to_decimal(pedido.saldo_pendiente)

    if total <= 0:
        return ESTADO_PEDIDO_BORRADOR
    if saldo <= Decimal('0.00'):
        return ESTADO_PEDIDO_PAGADO
    if total_pagado > 0:
        return ESTADO_PEDIDO_PAGO_PARCIAL
    return ESTADO_PEDIDO_PENDIENTE_SENA


def registrar_historial(pedido: PedidoCliente, descripcion: str, tipo_evento: str, id_usuario: int | None = None):
    evento = PedidoClienteHistorial(
        id_pedido=pedido.id_pedido,
        id_usuario=id_usuario,
        tipo_evento=tipo_evento,
        descripcion=_clean_text(descripcion, 255),
    )
    db.session.add(evento)
    return evento


def crear_pedido(*, id_cliente: int, id_usuario: int, observaciones: str = '', descuento_monto=0) -> PedidoCliente:
    cliente = Cliente.query.filter_by(id_cliente=id_cliente, activo=True).first()
    if not cliente:
        raise ValueError('Debe seleccionar un cliente valido.')

    pedido = PedidoCliente(
        id_cliente=cliente.id_cliente,
        id_usuario_creacion=id_usuario,
        id_usuario_modificacion=id_usuario,
        estado=ESTADO_PEDIDO_BORRADOR,
        observaciones=(observaciones or '').strip() or None,
        descuento_monto=max(Decimal('0'), _to_decimal(descuento_monto)),
        total_pagado=Decimal('0'),
    )
    db.session.add(pedido)
    db.session.flush()
    if not pedido.numero_pedido:
        pedido.numero_pedido = pedido.id_pedido
    recalcular_totales_pedido(pedido)
    registrar_historial(pedido, 'Pedido creado en borrador.', 'creacion', id_usuario=id_usuario)
    return pedido


def actualizar_pedido_base(pedido: PedidoCliente, *, id_cliente: int, id_usuario: int, observaciones: str = '', descuento_monto=0):
    if pedido_esta_bloqueado(pedido):
        raise ValueError('El pedido no se puede editar en su estado actual.')

    cliente = Cliente.query.filter_by(id_cliente=id_cliente, activo=True).first()
    if not cliente:
        raise ValueError('Debe seleccionar un cliente valido.')

    pedido.id_cliente = cliente.id_cliente
    pedido.id_usuario_modificacion = id_usuario
    pedido.observaciones = (observaciones or '').strip() or None
    pedido.descuento_monto = max(Decimal('0'), _to_decimal(descuento_monto))
    recalcular_totales_pedido(pedido)
    registrar_historial(pedido, 'Se actualizaron los datos generales del pedido.', 'edicion', id_usuario=id_usuario)
    return pedido


def cambiar_estado_pedido(pedido: PedidoCliente, *, nuevo_estado: str, id_usuario: int):
    nuevo_estado = (nuevo_estado or '').strip()
    if nuevo_estado not in ESTADOS_GESTIONABLES_SPRINT_1:
        raise ValueError('Estado no permitido en este sprint.')
    if pedido.estado == nuevo_estado:
        return pedido
    if pedido.estado in ESTADOS_BLOQUEADOS_PEDIDO:
        raise ValueError('El pedido no puede cambiar de estado.')
    pedido.estado = nuevo_estado
    pedido.id_usuario_modificacion = id_usuario
    registrar_historial(
        pedido,
        f'Estado actualizado a {nuevo_estado.replace("_", " ")}.',
        'estado',
        id_usuario=id_usuario,
    )
    return pedido


def reabrir_pedido(pedido: PedidoCliente, *, id_usuario: int):
    estado_actual = (pedido.estado or '').strip()
    if estado_actual != ESTADO_PEDIDO_CANCELADO:
        raise ValueError('Solo se pueden reabrir pedidos cancelados.')
    if int(getattr(pedido, 'id_venta_generada', 0) or 0) > 0:
        raise ValueError('No se puede reabrir un pedido que ya fue convertido en venta.')

    recalcular_totales_pedido(pedido)
    nuevo_estado = _resolver_estado_reapertura(pedido)
    pedido.estado = nuevo_estado
    pedido.id_usuario_modificacion = id_usuario
    registrar_historial(
        pedido,
        f'Pedido reabierto desde cancelado a {nuevo_estado.replace("_", " ")}.',
        'reapertura',
        id_usuario=id_usuario,
    )
    return pedido


def agregar_item_pedido(
    pedido: PedidoCliente,
    *,
    id_producto: int,
    cantidad: int,
    precio_unitario,
    id_usuario: int,
    observaciones: str = '',
):
    if not pedido_permite_edicion(pedido):
        raise ValueError('El pedido no permite agregar items en su estado actual.')

    producto = obtener_producto_activo_bloqueado(id_producto)
    if not producto:
        raise ValueError('Debe seleccionar un producto valido.')

    cantidad = _to_int(cantidad)
    if cantidad <= 0:
        raise ValueError('La cantidad debe ser mayor a cero.')

    precio = _to_decimal(precio_unitario if precio_unitario not in (None, '') else producto.precio_venta)
    if precio <= 0:
        raise ValueError('El precio unitario debe ser mayor a cero.')
    _validar_reserva_stock_producto(producto, cantidad)

    detalle = PedidoClienteDetalle(
        id_pedido=pedido.id_pedido,
        id_producto=producto.id_producto,
        cantidad=cantidad,
        precio_unitario=precio.quantize(Decimal('0.01')),
        porcentaje_iva=int(getattr(producto, 'porcentaje_iva', 10) or 10),
        producto_codigo_snapshot=producto.codigo,
        producto_nombre_snapshot=producto.nombre,
        observaciones=_clean_text(observaciones, 250) or None,
    )
    db.session.add(detalle)
    db.session.flush()
    recalcular_totales_pedido(pedido)
    pedido.id_usuario_modificacion = id_usuario
    registrar_historial(
        pedido,
        f'Se agrego {cantidad} x {producto.nombre}.',
        'item_agregado',
        id_usuario=id_usuario,
    )
    return detalle


def actualizar_item_pedido(
    pedido: PedidoCliente,
    item: PedidoClienteDetalle,
    *,
    cantidad: int,
    precio_unitario,
    id_usuario: int,
    observaciones: str = '',
):
    if pedido.id_pedido != item.id_pedido:
        raise ValueError('El item no pertenece al pedido indicado.')
    if not pedido_permite_edicion(pedido):
        raise ValueError('El pedido no permite editar items en su estado actual.')

    cantidad = _to_int(cantidad)
    if cantidad <= 0:
        raise ValueError('La cantidad debe ser mayor a cero.')

    precio = _to_decimal(precio_unitario)
    if precio <= 0:
        raise ValueError('El precio unitario debe ser mayor a cero.')
    producto = obtener_producto_activo_bloqueado(int(item.id_producto))
    if producto is None:
        raise ValueError('El producto del item ya no esta disponible.')
    _validar_reserva_stock_producto(producto, cantidad, excluir_item_id=int(item.id_detalle_pedido))

    item.cantidad = cantidad
    item.precio_unitario = precio.quantize(Decimal('0.01'))
    item.observaciones = _clean_text(observaciones, 250) or None
    pedido.id_usuario_modificacion = id_usuario
    recalcular_totales_pedido(pedido)
    registrar_historial(
        pedido,
        f'Se actualizo el item {item.producto_nombre_snapshot}.',
        'item_editado',
        id_usuario=id_usuario,
    )
    return item


def eliminar_item_pedido(pedido: PedidoCliente, item: PedidoClienteDetalle, *, id_usuario: int):
    if pedido.id_pedido != item.id_pedido:
        raise ValueError('El item no pertenece al pedido indicado.')
    if not pedido_permite_edicion(pedido):
        raise ValueError('El pedido no permite eliminar items en su estado actual.')

    nombre = item.producto_nombre_snapshot
    db.session.delete(item)
    pedido.id_usuario_modificacion = id_usuario
    recalcular_totales_pedido(pedido)
    registrar_historial(
        pedido,
        f'Se elimino el item {nombre}.',
        'item_eliminado',
        id_usuario=id_usuario,
    )


def buscar_productos_para_pedido(query: str, limit: int = 20):
    q = (query or '').strip()
    consulta = Producto.query.filter_by(activo=True)
    if q:
        like = f'%{q}%'
        consulta = consulta.filter(
            db.or_(
                Producto.nombre.ilike(like),
                Producto.codigo.ilike(like),
                Producto.marca.ilike(like),
                Producto.modelo.ilike(like),
            )
        )
    productos = consulta.order_by(Producto.nombre.asc()).limit(max(1, min(limit, 50))).all()
    for producto in productos:
        reservado = 0 if bool(getattr(producto, 'es_servicio', False)) else obtener_stock_reservado_producto(int(producto.id_producto))
        setattr(producto, 'stock_reservado_pedidos', reservado)
        setattr(
            producto,
            'stock_disponible_pedidos',
            int(getattr(producto, 'stock_actual', 0) or 0) - reservado if not bool(getattr(producto, 'es_servicio', False)) else None,
        )
    return productos
