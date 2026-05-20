import json

from app.services.ia_backoffice.metricas_negocio_presenter import respuesta_tool_metricas


def _formatear_candidato(nombre_tool: str, candidato: dict) -> str:
    if nombre_tool == 'cliente_detalle_360':
        return (
            f"- {candidato.get('id_cliente')} | {candidato.get('nombre') or 'Sin nombre'}"
            f" | RUC/CI: {candidato.get('ruc_ci') or '-'}"
            f" | Tel: {candidato.get('telefono') or '-'}"
        )
    if nombre_tool == 'producto_detalle_360':
        return (
            f"- {candidato.get('id_producto')} | {candidato.get('codigo') or '-'}"
            f" | {candidato.get('nombre') or 'Sin nombre'}"
            f" | Stock: {candidato.get('stock_actual') or 0}"
        )
    if nombre_tool == 'detalle_venta_documento':
        return (
            f"- {candidato.get('id_venta')} | {candidato.get('numero_comprobante') or 'Sin nro'}"
            f" | Fecha: {candidato.get('fecha_venta') or '-'}"
            f" | Cliente: {candidato.get('cliente') or '-'}"
        )
    return f"- {json.dumps(candidato, ensure_ascii=False, default=str)}"


def _formatear_guaranies(monto) -> str:
    try:
        return f"Gs. {float(monto or 0):,.0f}".replace(',', '.')
    except Exception:
        return 'Gs. 0'


def _respuesta_ventas_ranking_mensual(resultado_tool: dict) -> str | None:
    data = resultado_tool.get('data')
    if not isinstance(data, dict):
        return None
    mejor_mes = data.get('mejor_mes')
    detalle = data.get('detalle_cronologico') or []
    if not mejor_mes:
        return f"No hay ventas completadas en {data.get('periodo_label') or 'el periodo consultado'}."

    lineas = [
        (
            f"Hasta {data.get('hasta')}, el mes con mas ventas fue {mejor_mes.get('mes_nombre', '').lower()}"
            f" con {_formatear_guaranies(mejor_mes.get('total_ventas'))}."
        ),
        '',
        'Detalle por mes:',
    ]
    for item in detalle:
        lineas.append(f"- {item.get('mes_nombre')}: {_formatear_guaranies(item.get('total_ventas'))} en {int(item.get('cantidad_ventas') or 0)} ventas")
    return '\n'.join(lineas)


def _respuesta_inventario_resumen(resultado_tool: dict) -> str | None:
    data = resultado_tool.get('data')
    if not isinstance(data, dict):
        return None
    return '\n'.join([
        f"Inventario activo: {int(data.get('productos_activos') or 0)} productos.",
        f"Stock bajo: {int(data.get('productos_stock_bajo') or 0)} productos.",
        f"Sin stock: {int(data.get('productos_sin_stock') or 0)} productos.",
        f"Valor a costo: {_formatear_guaranies(data.get('valor_stock_costo'))}.",
    ])


def _respuesta_recomendaciones_crecimiento(resultado_tool: dict) -> str | None:
    data = resultado_tool.get('data')
    if not isinstance(data, dict):
        return None
    metricas = data.get('metricas') or {}
    lineas = [
        f"Para vender mas, enfocaria las acciones en {data.get('periodo_label') or 'el periodo consultado'}.",
        f"Ventas: {_formatear_guaranies(metricas.get('total_ventas'))} en {int(metricas.get('cantidad_ventas') or 0)} operaciones.",
        f"Ticket promedio: {_formatear_guaranies(metricas.get('ticket_promedio'))}.",
    ]
    margen = metricas.get('margen_bruto_pct')
    if margen is not None:
        lineas.append(f"Margen bruto estimado: {margen}%.")
    lineas.extend(['', 'Acciones recomendadas:'])
    for item in (data.get('recomendaciones') or [])[:5]:
        lineas.append(f"- {item.get('accion')}: {item.get('motivo')}")
    return '\n'.join(lineas)


def _respuesta_busqueda_entidad(resultado_tool: dict) -> str | None:
    data = resultado_tool.get('data')
    if not isinstance(data, dict):
        return None
    productos = ((data.get('resultados') or {}).get('productos') or [])[:10]
    if not productos:
        busqueda = data.get('busqueda') or 'esa busqueda'
        return f"No encontre productos para \"{busqueda}\". Proba con marca, modelo, codigo o una palabra mas corta."
    lineas = [f"Encontre {len(productos)} producto(s) para \"{data.get('busqueda') or ''}\":"]
    for producto in productos:
        lineas.append(
            f"- {producto.get('id_producto')} | {producto.get('codigo') or '-'}"
            f" | {producto.get('nombre') or 'Sin nombre'}"
            f" | Stock: {int(producto.get('stock_actual') or 0)}"
        )
    return '\n'.join(lineas)


def _respuesta_fidelizacion_resumen(resultado_tool: dict) -> str | None:
    data = resultado_tool.get('data')
    if not isinstance(data, dict):
        return None

    regla = data.get('regla') or {}
    beneficio = data.get('beneficio') or {}
    metricas = data.get('metricas') or {}
    clientes = data.get('clientes') or []
    flujo = data.get('flujo') or []
    lineas = [
        (
            f"Fidelizacion {'activa' if data.get('activa') else 'pausada'}: cada "
            f"{int(regla.get('compras_requeridas') or 0)} compra(s) dentro de "
            f"{int(regla.get('compras_ventana_dias') or 0)} dia(s) libera "
            f"{int(regla.get('premios_por_objetivo') or 0)} beneficio(s)."
        ),
        f"Beneficio actual: {beneficio.get('resumen') or 'Sin definir'}.",
        f"Modo: {regla.get('modo_generacion_label') or 'No definido'}.",
        f"Vigencia: {int(beneficio.get('vigencia_dias') or 0)} dia(s).",
        (
            'Uso en POS: si, se puede aplicar como descuento o saldo a favor.'
            if beneficio.get('pos_aplicable')
            else 'Uso en POS: no, este beneficio se canjea fuera del descuento automatico.'
        ),
        (
            f"Panel actual: {int(metricas.get('clientes_con_saldo') or 0)} cliente(s) con saldo o historial, "
            f"{int(metricas.get('beneficios_disponibles_total') or 0)} beneficio(s) disponibles."
        ),
    ]
    if flujo:
        lineas.append('')
        lineas.append('Flujo:')
        for item in flujo[:3]:
            lineas.append(f"- {item}")
    if clientes:
        lineas.append('')
        lineas.append('Clientes con saldo/historial (muestra):')
        for item in clientes[:8]:
            lineas.append(
                f"- {int(item.get('id_cliente') or 0)} | {item.get('nombre') or 'Sin nombre'}"
                f" | Beneficios disponibles: {int(item.get('beneficios_disponibles') or 0)}"
                f" | Compras acumuladas: {int(item.get('compras_acumuladas') or 0)}"
            )
    return '\n'.join(lineas)


def _respuesta_modulo_funcionamiento(resultado_tool: dict) -> str | None:
    data = resultado_tool.get('data')
    if not isinstance(data, dict):
        return None
    if data.get('encontrado') is False:
        sugerencias = data.get('sugerencias') or []
        if sugerencias:
            return 'No identifique bien el modulo. Proba con uno de estos nombres: ' + ', '.join(sugerencias[:5]) + '.'
        return 'No pude identificar ese modulo. Decime el nombre exacto que ves en el sistema y te lo explico.'

    lineas = [
        f"{data.get('label') or 'Modulo'}: {data.get('summary') or 'Modulo funcional del sistema.'}",
    ]
    funciones = data.get('funciones_clave') or []
    if funciones:
        lineas.append('')
        lineas.append('Que se puede hacer:')
        for item in funciones[:4]:
            lineas.append(f"- {item.rstrip('.')}.")
    flujo = data.get('flujo_resumen') or []
    if flujo:
        lineas.append('')
        lineas.append('Como se usa normalmente:')
        for item in flujo[:4]:
            lineas.append(f"- {item}")
    sensibles = data.get('acciones_sensibles') or []
    if sensibles:
        lineas.append('')
        lineas.append('Acciones mas sensibles:')
        for item in sensibles[:3]:
            lineas.append(f"- {item.rstrip('.')}.")
    return '\n'.join(lineas)


def respuesta_tool_directa(nombre_tool: str, resultado_tool: dict) -> str | None:
    if not isinstance(resultado_tool, dict):
        return None
    if resultado_tool.get('ok') is False:
        if str(resultado_tool.get('error') or '').startswith('sin_permiso'):
            return 'No tengo permiso para consultar esos datos en este usuario.'
        if resultado_tool.get('error') == 'tool_no_encontrada':
            return 'No pude ejecutar esa consulta interna porque la tool no esta disponible.'
        return None

    data = resultado_tool.get('data')
    if not isinstance(data, dict):
        return None
    if nombre_tool == 'ventas_ranking_mensual':
        return _respuesta_ventas_ranking_mensual(resultado_tool)
    if nombre_tool == 'inventario_resumen':
        return _respuesta_inventario_resumen(resultado_tool)
    if nombre_tool == 'ventas_recomendaciones_crecimiento':
        return _respuesta_recomendaciones_crecimiento(resultado_tool)
    if nombre_tool == 'buscar_entidad_backoffice':
        return _respuesta_busqueda_entidad(resultado_tool)
    if nombre_tool == 'modulo_funcionamiento':
        return _respuesta_modulo_funcionamiento(resultado_tool)
    if nombre_tool == 'fidelizacion_resumen':
        return _respuesta_fidelizacion_resumen(resultado_tool)

    respuesta_metricas = respuesta_tool_metricas(nombre_tool, resultado_tool)
    if respuesta_metricas:
        return respuesta_metricas

    if data.get('requiere_seleccion') and data.get('candidatos'):
        entidad = {
            'cliente_detalle_360': 'clientes',
            'producto_detalle_360': 'productos',
            'detalle_venta_documento': 'documentos de venta',
            'proveedor_detalle_360': 'proveedores',
            'presupuesto_detalle': 'presupuestos',
        }.get(nombre_tool, 'resultados')
        lineas = [f'Encontre varios {entidad}. Decime cual queres abrir por ID o copia una referencia mas exacta.']
        for candidato in data.get('candidatos', [])[:5]:
            lineas.append(_formatear_candidato(nombre_tool, candidato))
        return '\n'.join(lineas)

    if data.get('encontrado') is False:
        errores = {
            'cliente_no_encontrado': 'No encontre ese cliente. Proba con nombre, RUC/CI, telefono o ID.',
            'producto_no_encontrado': 'No encontre ese producto. Proba con nombre, codigo, codigo de barras o ID.',
            'venta_no_encontrada': 'No encontre esa venta. Proba con numero de comprobante, ticket, referencia o ID.',
        }
        return errores.get(data.get('error'))
    return None
