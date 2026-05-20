from decimal import Decimal

from app.models import Producto
from pedidos.services.pago_service import registrar_pago_pedido
from pedidos.services.pedido_service import (
    _clean_text,
    _to_decimal,
    _to_int,
    agregar_item_pedido,
    crear_pedido,
)


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal('0.01'))


def _serializar_item_preview(producto: Producto, cantidad: int, precio_unitario: Decimal, observaciones: str) -> dict:
    subtotal = _money(precio_unitario * Decimal(cantidad))
    return {
        'id_producto': int(producto.id_producto),
        'codigo': producto.codigo or '',
        'nombre': producto.nombre or '',
        'cantidad': int(cantidad),
        'precio_unitario': float(_money(precio_unitario)),
        'subtotal': float(subtotal),
        'observaciones': observaciones or '',
    }


def extraer_items_iniciales_desde_form(form) -> list[dict]:
    ids = form.getlist('items_id_producto')
    cantidades = form.getlist('items_cantidad')
    precios = form.getlist('items_precio_unitario')
    observaciones = form.getlist('items_observaciones')

    total_rows = max(len(ids), len(cantidades), len(precios), len(observaciones))
    if total_rows <= 0:
        return []

    filas = []
    producto_ids = set()

    for index in range(total_rows):
        raw_id = ids[index].strip() if index < len(ids) and ids[index] is not None else ''
        raw_cantidad = cantidades[index].strip() if index < len(cantidades) and cantidades[index] is not None else ''
        raw_precio = precios[index].strip() if index < len(precios) and precios[index] is not None else ''
        raw_obs = observaciones[index] if index < len(observaciones) and observaciones[index] is not None else ''
        observacion_limpia = _clean_text(raw_obs, 250)

        if not any([raw_id, raw_cantidad, raw_precio, observacion_limpia]):
            continue

        id_producto = _to_int(raw_id)
        cantidad = _to_int(raw_cantidad)
        if id_producto <= 0:
            raise ValueError('Hay un item sin producto seleccionado.')
        if cantidad <= 0:
            raise ValueError('La cantidad de cada producto debe ser mayor a cero.')

        filas.append(
            {
                'id_producto': id_producto,
                'cantidad': cantidad,
                'precio_unitario_raw': raw_precio,
                'observaciones': observacion_limpia,
            }
        )
        producto_ids.add(id_producto)

    if not filas:
        return []

    productos = {
        int(producto.id_producto): producto
        for producto in Producto.query.filter(Producto.id_producto.in_(tuple(producto_ids)), Producto.activo.is_(True)).all()
    }

    items = []
    for fila in filas:
        producto = productos.get(int(fila['id_producto']))
        if producto is None:
            raise ValueError('Uno de los productos seleccionados ya no esta disponible.')
        precio_unitario = _to_decimal(
            fila['precio_unitario_raw'] if fila['precio_unitario_raw'] not in (None, '') else producto.precio_venta
        )
        if precio_unitario <= 0:
            raise ValueError(f'El precio del producto {producto.nombre} debe ser mayor a cero.')
        items.append(
            _serializar_item_preview(
                producto,
                int(fila['cantidad']),
                precio_unitario,
                fila['observaciones'],
            )
        )
    return items


def construir_resumen_inicial(*, items: list[dict], descuento_monto=0, pago_inicial=0) -> dict:
    subtotal = sum((_to_decimal(item.get('subtotal', 0)) for item in items), Decimal('0'))
    descuento = max(Decimal('0'), _to_decimal(descuento_monto))
    total = max(Decimal('0'), subtotal - descuento)
    pago = max(Decimal('0'), _to_decimal(pago_inicial))
    saldo = max(Decimal('0'), total - pago)
    return {
        'subtotal': float(_money(subtotal)),
        'descuento': float(_money(descuento)),
        'total': float(_money(total)),
        'pago_inicial': float(_money(pago)),
        'saldo': float(_money(saldo)),
    }


def crear_pedido_completo(
    *,
    id_cliente: int,
    id_usuario: int,
    observaciones: str = '',
    descuento_monto=0,
    items: list[dict] | None = None,
    pago_inicial: dict | None = None,
    sesion_caja=None,
):
    pedido = crear_pedido(
        id_cliente=id_cliente,
        id_usuario=id_usuario,
        observaciones=observaciones,
        descuento_monto=descuento_monto,
    )

    items = items or []
    for item in items:
        agregar_item_pedido(
            pedido,
            id_producto=int(item['id_producto']),
            cantidad=int(item['cantidad']),
            precio_unitario=item['precio_unitario'],
            observaciones=item.get('observaciones', ''),
            id_usuario=id_usuario,
        )

    pago_registrado = None
    monto_pago_inicial = _to_decimal((pago_inicial or {}).get('monto'))
    if monto_pago_inicial > 0:
        if not items:
            raise ValueError('Debe agregar al menos un producto antes de registrar una seña o pago inicial.')
        pago_registrado = registrar_pago_pedido(
            pedido,
            id_metodo_pago=(pago_inicial or {}).get('id_metodo_pago'),
            monto=monto_pago_inicial,
            tipo_pago=(pago_inicial or {}).get('tipo_pago'),
            referencia=(pago_inicial or {}).get('referencia', ''),
            observaciones=(pago_inicial or {}).get('observaciones', ''),
            id_usuario=id_usuario,
            sesion=sesion_caja,
        )

    return {
        'pedido': pedido,
        'pago_inicial': pago_registrado,
    }
