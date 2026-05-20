from app.utils.auditoria_utils import registrar_auditoria


def pedido_snapshot(pedido) -> dict:
    return {
        'id_pedido': int(getattr(pedido, 'id_pedido', 0) or 0),
        'numero_pedido': getattr(pedido, 'numero_pedido_display', ''),
        'id_cliente': int(getattr(pedido, 'id_cliente', 0) or 0),
        'estado': (getattr(pedido, 'estado', '') or '').strip(),
        'subtotal': float(getattr(pedido, 'subtotal', 0) or 0),
        'descuento_monto': float(getattr(pedido, 'descuento_monto', 0) or 0),
        'total': float(getattr(pedido, 'total', 0) or 0),
        'total_pagado': float(getattr(pedido, 'total_pagado', 0) or 0),
        'saldo_pendiente': float(getattr(pedido, 'saldo_pendiente', 0) or 0),
        'id_venta_generada': int(getattr(pedido, 'id_venta_generada', 0) or 0) or None,
        'observaciones': getattr(pedido, 'observaciones', None),
    }


def item_snapshot(item) -> dict:
    return {
        'id_detalle_pedido': int(getattr(item, 'id_detalle_pedido', 0) or 0),
        'id_producto': int(getattr(item, 'id_producto', 0) or 0),
        'producto': getattr(item, 'producto_nombre_snapshot', '') or '',
        'codigo': getattr(item, 'producto_codigo_snapshot', '') or '',
        'cantidad': int(getattr(item, 'cantidad', 0) or 0),
        'precio_unitario': float(getattr(item, 'precio_unitario', 0) or 0),
        'subtotal': float(getattr(item, 'subtotal', 0) or 0),
        'observaciones': getattr(item, 'observaciones', None),
    }


def pago_snapshot(pago) -> dict:
    metodo = getattr(getattr(pago, 'metodo', None), 'nombre', None)
    return {
        'id_pago_pedido': int(getattr(pago, 'id_pago_pedido', 0) or 0),
        'tipo_pago': getattr(pago, 'tipo_pago', '') or '',
        'monto': float(getattr(pago, 'monto', 0) or 0),
        'metodo': metodo or '',
        'referencia': getattr(pago, 'referencia', None),
        'id_movimiento_caja': int(getattr(pago, 'id_movimiento_caja', 0) or 0) or None,
        'id_sesion_caja': int(getattr(pago, 'id_sesion_caja', 0) or 0) or None,
    }


def venta_snapshot(venta) -> dict:
    return {
        'id_venta': int(getattr(venta, 'id_venta', 0) or 0),
        'id_cliente': int(getattr(venta, 'id_cliente', 0) or 0),
        'total': float(getattr(venta, 'total', 0) or 0),
        'estado': getattr(venta, 'estado', '') or '',
        'tipo_venta': getattr(venta, 'tipo_venta', '') or '',
    }


def auditar_evento_pedido(
    *,
    accion: str,
    descripcion: str,
    pedido,
    datos_anteriores: dict | None = None,
    datos_nuevos: dict | None = None,
    referencia_tipo: str = 'pedido_cliente',
    referencia_id: int | None = None,
):
    return registrar_auditoria(
        accion=accion,
        modulo='pedidos',
        descripcion=descripcion,
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id if referencia_id is not None else int(getattr(pedido, 'id_pedido', 0) or 0),
        datos_anteriores=datos_anteriores,
        datos_nuevos=datos_nuevos,
        commit=False,
    )
