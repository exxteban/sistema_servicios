from __future__ import annotations

from datetime import datetime
from io import BytesIO

from flask import current_app, make_response, render_template


def _format_money(value) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    return f'Gs. {number:,.0f}'.replace(',', '.')


def _build_pdf_context(panel: dict) -> dict:
    comparativo = panel.get('comparativo') or {}
    categorias_resumen = []
    for categoria in panel.get('categorias_resumen') or []:
        categorias_resumen.append(
            {
                'label': categoria.get('label') or 'Otros',
                'cantidad': int(categoria.get('cantidad') or 0),
                'pagados': int(categoria.get('pagados') or 0),
                'pendientes': int(categoria.get('pendientes') or 0),
                'total_estimado': _format_money(categoria.get('total_estimado')),
                'total_pagado': _format_money(categoria.get('total_pagado')),
                'total_pendiente': _format_money(categoria.get('total_pendiente')),
                'porcentaje_pagado': f"{float(categoria.get('porcentaje_pagado') or 0):.2f}%",
            }
        )

    items = []
    for item in panel.get('items') or []:
        pago = item.get('pago')
        monto_pagado = item.get('monto_pagado') or 0
        monto_pendiente = item.get('monto_estimado') if item.get('estado_panel') in {'pendiente', 'vencido'} else 0
        items.append(
            {
                'nombre': item['gasto'].nombre,
                'categoria': (item['gasto'].categoria or 'otros').replace('_', ' ').title(),
                'vencimiento': item['fecha_vencimiento'].strftime('%d/%m/%Y') if item.get('fecha_vencimiento') else '-',
                'estado': (item.get('estado_panel') or '').replace('_', ' ').title(),
                'alerta': item.get('alerta', {}).get('texto') or '',
                'estimado': _format_money(item.get('monto_estimado')),
                'pagado': _format_money(monto_pagado) if monto_pagado else '-',
                'pendiente': _format_money(monto_pendiente) if monto_pendiente else '-',
                'medio_pago': 'Caja' if pago and pago.pagado_desde_caja else 'Fuera de caja',
                'comprobante': pago.numero_comprobante if pago and pago.numero_comprobante else '-',
            }
        )

    return {
        'generado_el': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'periodo': panel.get('periodo') or '',
        'categoria': panel.get('categoria') or 'Todas',
        'estado': panel.get('estado') or 'Todos',
        'total_estimado': _format_money(panel.get('total_estimado')),
        'total_pagado': _format_money(panel.get('total_pagado')),
        'total_pendiente': _format_money(panel.get('total_pendiente')),
        'vencidos': int(panel.get('vencidos') or 0),
        'alertas_activas': int(panel.get('alertas_activas') or 0),
        'comparativo': {
            'cantidad_items': int(comparativo.get('cantidad_items') or 0),
            'cantidad_pagados': int(comparativo.get('cantidad_pagados') or 0),
            'cantidad_pendientes': int(comparativo.get('cantidad_pendientes') or 0),
            'porcentaje_pagado': f"{float(comparativo.get('porcentaje_pagado') or 0):.2f}%",
            'porcentaje_pendiente': f"{float(comparativo.get('porcentaje_pendiente') or 0):.2f}%",
            'desviacion': _format_money(abs(float(comparativo.get('desviacion') or 0))),
            'estado_desviacion': comparativo.get('estado_desviacion') or 'exacto',
        },
        'categorias_resumen': categorias_resumen,
        'items': items,
    }


def generar_pdf_panel_gastos_corrientes(panel: dict) -> bytes:
    try:
        from xhtml2pdf import pisa
    except Exception as exc:
        raise RuntimeError('xhtml2pdf no está disponible para generar el reporte PDF.') from exc

    html = render_template(
        'gastos_corrientes/reporte_pdf.html',
        reporte=_build_pdf_context(panel),
    )
    pdf_buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=pdf_buffer, encoding='UTF-8')
    if status.err:
        current_app.logger.error('No se pudo generar el PDF de gastos corrientes para %s', panel.get('periodo'))
        raise RuntimeError('No se pudo generar el PDF del reporte de gastos corrientes.')
    return pdf_buffer.getvalue()


def generar_pdf_response_panel_gastos_corrientes(panel: dict):
    filename = f'gastos_corrientes_{panel.get("periodo") or "reporte"}.pdf'
    response = make_response(generar_pdf_panel_gastos_corrientes(panel))
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
