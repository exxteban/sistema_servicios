from flask import current_app


def resumen_pedidos_gastronomia_cierre():
    """Obtiene pedidos gastronomicos impagos relevantes para el cierre."""
    try:
        from gastronomia.services.access import cliente_id_actual_gastronomia
        from gastronomia.services.caja_service import resumen_pedidos_impagos_para_cierre
    except Exception:
        return None

    try:
        cliente_id = cliente_id_actual_gastronomia()
    except Exception:
        cliente_id = None
    if not cliente_id:
        return None

    try:
        resumen = resumen_pedidos_impagos_para_cierre(cliente_id)
    except Exception:
        current_app.logger.exception('No se pudo calcular pedidos gastronomicos impagos para el cierre de caja')
        return None

    if not resumen.get('hay_en_curso') and not resumen.get('hay_terminados'):
        return None
    return resumen


def resumen_pedidos_gastronomia_texto(pedidos):
    partes = []
    for pedido in pedidos[:5]:
        etiqueta = pedido.get('codigo_entrega') or f"#{pedido.get('id_pedido')}"
        referencia = pedido.get('mesa') or pedido.get('nombre_cliente') or pedido.get('tipo_pedido') or ''
        referencia = (referencia or '').strip()
        monto = f"₲ {float(pedido.get('total') or 0):,.0f}"
        if referencia:
            partes.append(f'{etiqueta} · {referencia} · {monto}')
        else:
            partes.append(f'{etiqueta} · {monto}')
    return ' | '.join(partes)


def mensaje_confirmacion_pedidos_terminados(resumen, form):
    if not resumen or not resumen.get('hay_terminados') or form.get('confirmar_pedidos_pendientes'):
        return None
    detalle = resumen_pedidos_gastronomia_texto(resumen['terminados'])
    sufijo = '...' if len(resumen['terminados']) > 5 else ''
    return (
        'Hay pedidos gastronómicos entregados o listos sin cobrar. '
        f'Confirme que los deja pendientes para poder cerrar: {detalle}{sufijo}.'
    )


def agregar_observacion_pedidos_terminados(observaciones, resumen):
    if not resumen or not resumen.get('hay_terminados'):
        return observaciones
    cant = len(resumen['terminados'])
    monto = resumen.get('total_terminados') or 0
    nota = (
        f'Cierre con {cant} pedido(s) gastronómico(s) entregados sin cobrar '
        f'por ₲ {monto:,.0f} confirmados como pendientes.'
    )
    return (observaciones + '\n' if observaciones else '') + nota
