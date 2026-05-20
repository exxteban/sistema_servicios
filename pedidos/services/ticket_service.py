from app.models import Configuracion


def _as_float(value, default=0.0):
    try:
        return float(value or 0)
    except Exception:
        return float(default)


def _agregar_pago_resumen(items, nombre, monto):
    nombre_normalizado = str(nombre or '').strip().lower() or 'sin metodo'
    for item in items:
        if str(item.get('nombre') or '').strip().lower() != nombre_normalizado:
            continue
        item['monto'] = _as_float(item.get('monto')) + _as_float(monto)
        item['cantidad'] = int(item.get('cantidad') or 0) + 1
        return
    items.append(
        {
            'nombre': nombre or 'Sin metodo',
            'monto': _as_float(monto),
            'cantidad': 1,
        }
    )


def build_pedido_ticket_context(
    pedido,
    *,
    preview=False,
    embedded=False,
    return_to='',
    id_pago_destacado=None,
    close_only=False,
):
    empresa = {
        'nombre': Configuracion.obtener('nombre_empresa', '') or '',
        'ruc': Configuracion.obtener('ruc_empresa', '') or '',
        'direccion': Configuracion.obtener('direccion_empresa', '') or '',
        'telefono': Configuracion.obtener('telefono_empresa', '') or '',
    }
    footer_text = Configuracion.obtener('ticket_footer_text', 'Gracias por su compra') or 'Gracias por su compra'
    paper_width_mm = Configuracion.obtener_int('ticket_paper_width_mm', 58)
    if paper_width_mm not in (48, 58, 80):
        paper_width_mm = 58

    items = list(pedido.detalles.all())
    pagos = list(pedido.pagos.filter_by(estado='activo').all())
    pago_destacado = None
    if id_pago_destacado not in (None, ''):
        try:
            id_pago_destacado = int(id_pago_destacado)
        except (TypeError, ValueError):
            id_pago_destacado = None
    if id_pago_destacado:
        for pago in pagos:
            if int(getattr(pago, 'id_pago_pedido', 0) or 0) == id_pago_destacado:
                pago_destacado = pago
                break
    pagos_resumen = []
    for pago in pagos:
        metodo_nombre = getattr(getattr(pago, 'metodo', None), 'nombre', None) or 'Sin metodo'
        _agregar_pago_resumen(pagos_resumen, metodo_nombre, pago.monto)
    pagos_resumen.sort(key=lambda item: str(item.get('nombre') or '').lower())

    return {
        'pedido': pedido,
        'items': items,
        'pagos': pagos,
        'pago_destacado': pago_destacado,
        'pagos_resumen': pagos_resumen,
        'empresa': empresa,
        'subtotal': _as_float(getattr(pedido, 'subtotal', 0)),
        'descuento': _as_float(getattr(pedido, 'descuento_monto', 0)),
        'total': _as_float(getattr(pedido, 'total', 0)),
        'total_pagado': _as_float(getattr(pedido, 'total_pagado', 0)),
        'saldo_pendiente': _as_float(getattr(pedido, 'saldo_pendiente', 0)),
        'preview': bool(preview),
        'embedded': bool(embedded),
        'return_to': return_to or '',
        'close_only': bool(close_only),
        'moneda_simbolo': '₲' if preview else 'Gs.',
        'footer_text': footer_text,
        'paper_width_mm': paper_width_mm,
    }
