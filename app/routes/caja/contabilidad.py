from io import BytesIO

from flask import flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.routes.caja import caja_bp
from app.routes.caja.common import _calcular_informe_contable_rango
from app.utils.pdf_runtime import import_pisa, is_arm_machine
from app.utils.helpers import now_local, parse_iso_date, today_local, utc_bounds_for_local_dates


def _build_modal_payload(detalles: list[dict] | None):
    def _serialize_rows(field: str):
        rows = []
        total = 0.0
        for detalle in detalles or []:
            monto = float((detalle or {}).get(field) or 0)
            if monto <= 0:
                continue

            fecha = (detalle or {}).get('fecha')
            fecha_label = fecha.strftime('%d/%m/%Y %H:%M') if hasattr(fecha, 'strftime') else ''
            rows.append(
                {
                    'fecha': fecha_label,
                    'concepto': (detalle or {}).get('concepto') or '',
                    'referencia': (detalle or {}).get('referencia') or '',
                    'detalle': (detalle or {}).get('detalle') or '',
                    'forma_pago': (detalle or {}).get('forma_pago') or '',
                    'monto': monto,
                }
            )
            total += monto
        return {'items': rows, 'total': total, 'count': len(rows)}

    return {
        'ingresos': _serialize_rows('entrada'),
        'egresos': _serialize_rows('salida'),
    }


@caja_bp.route('/contabilidad')
@login_required
def contabilidad():
    """Cierre contable por rango de fechas (ingresos - egresos)"""
    if not current_user.tiene_permiso('ver_caja'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver la contabilidad.', 'danger')
        return redirect(url_for('main.dashboard'))

    raw_desde = request.args.get('desde')
    raw_hasta = request.args.get('hasta')

    if raw_desde or raw_hasta:
        desde = parse_iso_date(raw_desde) or parse_iso_date(raw_hasta) or today_local()
        hasta = parse_iso_date(raw_hasta) or parse_iso_date(raw_desde) or desde
    else:
        hasta = today_local()
        desde = today_local().replace(day=1) if hasattr(today_local(), 'replace') else hasta

    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde

    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)

    informe = _calcular_informe_contable_rango(start_utc, end_utc)
    detalle_modal = _build_modal_payload(informe.get('detalles'))

    return render_template(
        'caja/contabilidad.html',
        desde=desde,
        hasta=hasta,
        detalle_modal=detalle_modal,
        **informe,
    )


@caja_bp.route('/contabilidad/imprimir')
@login_required
def contabilidad_imprimir():
    """Versión para imprimir del cierre contable"""
    if not current_user.tiene_permiso('ver_caja'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver la contabilidad.', 'danger')
        return redirect(url_for('main.dashboard'))

    raw_desde = request.args.get('desde')
    raw_hasta = request.args.get('hasta')

    if raw_desde or raw_hasta:
        desde = parse_iso_date(raw_desde) or parse_iso_date(raw_hasta) or today_local()
        hasta = parse_iso_date(raw_hasta) or parse_iso_date(raw_desde) or desde
    else:
        hasta = today_local()
        desde = today_local().replace(day=1) if hasattr(today_local(), 'replace') else hasta

    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde

    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)

    informe = _calcular_informe_contable_rango(start_utc, end_utc)

    return render_template(
        'caja/contabilidad_imprimir.html',
        desde=desde,
        hasta=hasta,
        **informe,
    )


@caja_bp.route('/contabilidad/pdf')
@login_required
def contabilidad_pdf():
    """Generar PDF del cierre contable (Server-side)"""
    try:
        pisa = import_pisa()
    except Exception:
        if not is_arm_machine():
            raise
        flash('La generacion de PDF no esta disponible en este entorno.', 'warning')
        return redirect(url_for('caja.contabilidad'))

    if not current_user.tiene_permiso('ver_caja'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver la contabilidad.', 'danger')
        return redirect(url_for('main.dashboard'))

    raw_desde = request.args.get('desde')
    raw_hasta = request.args.get('hasta')

    if raw_desde or raw_hasta:
        desde = parse_iso_date(raw_desde) or parse_iso_date(raw_hasta) or today_local()
        hasta = parse_iso_date(raw_hasta) or parse_iso_date(raw_desde) or desde
    else:
        hasta = today_local()
        desde = today_local().replace(day=1) if hasattr(today_local(), 'replace') else hasta

    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde

    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)

    informe = _calcular_informe_contable_rango(start_utc, end_utc)

    html = render_template(
        'caja/contabilidad_pdf.html',
        desde=desde,
        hasta=hasta,
        now=now_local(),
        **informe,
    )

    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

    if pisa_status.err:
        flash('Error al generar el PDF', 'danger')
        return redirect(url_for('caja.contabilidad'))

    pdf_buffer.seek(0)

    response = make_response(pdf_buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=contabilidad_{desde.strftime("%Y%m%d")}_{hasta.strftime("%Y%m%d")}.pdf'

    return response
