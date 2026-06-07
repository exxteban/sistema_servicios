def resumen_pendientes_para_cierre(pendientes):
    items = []
    for pendiente in pendientes[:5]:
        cliente = ((pendiente.cliente.nombre if pendiente.cliente else '') or '').strip() or 'Consumidor Final'
        tipo = 'Reparación' if pendiente.tipo_origen == 'reparacion' else 'Venta'
        if pendiente.tipo_origen == 'cobro_credito':
            tipo = 'Cobro crédito'
        elif pendiente.tipo_origen == 'pedido':
            tipo = 'Pedido'
        elif pendiente.tipo_origen == 'gastronomia':
            tipo = 'Pedido gastronomia'
        monto = f'₲ {float(pendiente.monto_total or 0):,.0f}'
        items.append(f'#{pendiente.id} {tipo} · {cliente} · {monto}')
    return ' | '.join(items)
