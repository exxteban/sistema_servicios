def _money(value) -> str:
    try:
        return f"Gs. {float(value or 0):,.0f}".replace(',', '.')
    except Exception:
        return 'Gs. 0'


def respuesta_tool_metricas(nombre_tool: str, resultado_tool: dict) -> str | None:
    data = resultado_tool.get('data') if isinstance(resultado_tool, dict) else None
    if not isinstance(data, dict):
        return None
    if nombre_tool == 'metricas_explicacion_negocio':
        if not data.get('encontrado'):
            return 'No tengo ese concepto registrado todavia. Proba con ganancia neta, ganancia bruta, margen bruto, resultado de caja o diferencia de cierre.'
        lineas = [
            f"{data.get('titulo')}: {data.get('definicion')}",
            f"Formula simple: {data.get('formula_resumida')}",
            f"Incluye: {', '.join(data.get('incluye') or [])}.",
            f"No incluye: {', '.join(data.get('no_incluye') or [])}.",
        ]
        if data.get('nota_sistema'):
            lineas.append(data.get('nota_sistema'))
        return '\n'.join(lineas)
    if nombre_tool == 'metricas_comparacion_negocio':
        if not data.get('encontrado'):
            return 'Necesito dos conceptos claros para comparar. Proba con ganancia neta vs resultado de caja o ganancia bruta vs resultado de caja.'
        lineas = [
            data.get('resumen_corto') or '',
            f"Diferencia clave: {data.get('diferencia_clave')}",
        ]
        for item in (data.get('cuando_no_coinciden') or [])[:3]:
            lineas.append(f"- {item}")
        if data.get('lectura_sistema'):
            lineas.append(data.get('lectura_sistema'))
        return '\n'.join([item for item in lineas if item])
    if nombre_tool != 'metricas_resumen_operativo':
        return None
    lineas = [f"Resumen operativo de {data.get('periodo_label') or 'ese periodo'}:"]
    if data.get('ventas_disponibles'):
        lineas.append(f"Ventas: {_money(data.get('ventas_total'))}.")
        lineas.append(f"Ganancia bruta estimada: {_money(data.get('ganancia_bruta_estimada'))}.")
        margen = data.get('margen_bruto_pct')
        if margen is not None:
            lineas.append(f"Margen bruto estimado: {margen}%.")
    if data.get('gastos_disponibles'):
        lineas.append(f"Gastos pagados: {_money(data.get('gastos_pagados'))}.")
        lineas.append(f"Gastos pendientes: {_money(data.get('gastos_pendientes'))}.")
    if data.get('caja_disponible'):
        lineas.append(f"Resultado de caja por movimientos: {_money(data.get('resultado_caja_movimientos'))}.")
    if data.get('resultado_operativo_aproximado') is not None:
        lineas.append(f"Resultado operativo aproximado: {_money(data.get('resultado_operativo_aproximado'))}.")
    lineas.append(data.get('nota_ganancia_neta') or '')
    return '\n'.join([item for item in lineas if item])
