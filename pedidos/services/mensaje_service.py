def _format_gs(value) -> str:
    return f'Gs. {format(float(value or 0), ",.0f").replace(",", ".")}'


def build_resumen_pedido_cliente(pedido) -> str:
    cliente = getattr(pedido, 'cliente', None)
    lineas = [
        f'Hola {((getattr(cliente, "nombre", None) or "cliente").strip())},',
        f'Aqui tienes el resumen de tu pedido {pedido.numero_pedido_display}:',
        '',
    ]

    items = list(pedido.detalles.all())
    if items:
        lineas.append('Items:')
        for item in items:
            lineas.append(
                f'- {int(item.cantidad or 0)} x {item.producto_nombre_snapshot}: {_format_gs(item.subtotal or 0)}'
            )
        lineas.append('')

    lineas.extend(
        [
            f'Estado: {pedido.estado_label}',
            f'Total: {_format_gs(pedido.total or 0)}',
            f'Total pagado: {_format_gs(pedido.total_pagado or 0)}',
            f'Saldo pendiente: {_format_gs(pedido.saldo_pendiente or 0)}',
        ]
    )

    if getattr(pedido, 'observaciones', None):
        lineas.extend(
            [
                '',
                f'Observaciones: {pedido.observaciones}',
            ]
        )

    if int(getattr(pedido, 'id_venta_generada', 0) or 0) > 0:
        lineas.extend(
            [
                '',
                f'Venta final generada: #{int(pedido.id_venta_generada)}',
            ]
        )

    lineas.extend(
        [
            '',
            'Gracias.',
        ]
    )
    return '\n'.join(lineas)
