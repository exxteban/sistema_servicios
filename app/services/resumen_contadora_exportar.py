"""Descargas del informe del mes para el/la contador/a: PDF y Excel completo.

- **PDF:** para leer, mandar y archivar. Carátula, liquidación, cuadro de
  IVA, pendientes y (si se pide) los anexos con cada comprobante.
- **Excel:** para trabajar. Una hoja de resumen y una por anexo, con las
  mismas columnas que el Excel de cada fila del detalle.

Los datos salen de `informe_del_mes`; acá sólo se les da forma.
"""
from flask import current_app, make_response, render_template

from app.services.resumen_contadora_detalle import tabla
from app.utils.pdf_runtime import generar_pdf_bytes

MESES = ('Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto',
         'Septiembre', 'Octubre', 'Noviembre', 'Diciembre')
COLUMNAS_CUADRO = ['Concepto', 'Cant.', 'Exentas', 'Gravadas 5%', 'IVA 5%', 'Gravadas 10%', 'IVA 10%', 'Total']


def _nombre_archivo(informe, extension, sufijo=''):
    return f"iva_{informe['primero'].strftime('%Y_%m')}{sufijo}.{extension}"


def respuesta_pdf(informe, con_anexos=True):
    """El PDF como descarga, o None si el servidor no puede generar PDFs."""
    html = render_template('contador/informe_pdf.html', i=informe, meses=MESES, con_anexos=con_anexos)
    contenido = generar_pdf_bytes(html)
    if contenido is None:
        current_app.logger.error('No se pudo generar el PDF del resumen de IVA %s', informe['primero'])
        return None
    respuesta = make_response(contenido)
    respuesta.headers['Content-Type'] = 'application/pdf'
    nombre = _nombre_archivo(informe, 'pdf', '' if con_anexos else '_resumen')
    respuesta.headers['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return respuesta


def _hoja_resumen(ws, informe):
    from app.services.reportes_excel import _llenar_hoja

    r, c = informe['resumen'], informe['cierre']
    filas = []
    for f in informe['cuadro']:
        signo = -1 if f['resta'] else 1
        b = f['b']
        filas.append([f['concepto'] + (' (resta)' if f['resta'] else ''), b['cantidad']]
                     + [signo * b[k] for k in ('exenta', 'base5', 'iva5', 'base10', 'iva10', 'total')])
    empresa = informe['empresa']
    subtitulo = f"{empresa['nombre'] or ''}{' · RUC ' + empresa['ruc'] if empresa['ruc'] else ''} · " \
                f"Del {r['desde'].strftime('%d/%m/%Y')} al {r['hasta'].strftime('%d/%m/%Y')}"
    _llenar_hoja(ws, f"Resumen de IVA · {MESES[informe['primero'].month - 1]} {informe['primero'].year}",
                 subtitulo, COLUMNAS_CUADRO, filas, money_cols=range(3, 9))
    if r['fe_activa'] and r['ambiente'] == 'test':
        ws.append(['Ambiente de PRUEBA (TEST): documentos sin validez fiscal.'])
    ws.append([])
    for etiqueta, valor in (('Débito fiscal', r['debito']), ('Crédito fiscal', r['credito']),
                            ('Saldo a favor del mes anterior', c['saldo_favor_anterior']),
                            ('Retenciones', c['retenciones']),
                            ('Saldo del mes (+ a pagar / − a favor)', c['saldo_final'])):
        ws.append([etiqueta, '', valor])
        ws.cell(row=ws.max_row, column=3).number_format = '#,##0'
    registro = c['registro']
    ws.append(['Estado', '', 'Presentado' if registro and registro.presentado else 'Abierto'])
    for titulo, textos in (('Pendiente para cerrar el mes', informe['pendientes']),
                           ('Para tener en cuenta', informe['avisos'])):
        if textos:
            ws.append([])
            ws.append([titulo])
            for texto in textos:
                ws.append([f'• {texto}'])


def respuesta_excel(informe):
    from app.services.reportes_excel import (
        OPENPYXL_DISPONIBLE,
        Workbook,
        _llenar_hoja,
        _respuesta_excel,
        _respuesta_no_disponible,
    )

    if not OPENPYXL_DISPONIBLE:
        return _respuesta_no_disponible()
    wb = Workbook()
    hoja = wb.active
    hoja.title = 'Resumen'
    _hoja_resumen(hoja, informe)
    periodo = f"{informe['resumen']['desde'].strftime('%d/%m/%Y')} al {informe['resumen']['hasta'].strftime('%d/%m/%Y')}"
    for detalle in informe['anexos']:
        headers, filas, montos = tabla(detalle)
        _llenar_hoja(wb.create_sheet(detalle['titulo'][:31]), detalle['titulo'], f'Período: {periodo}',
                     headers, filas, money_cols=montos)
    anuladas = informe['anuladas']
    _llenar_hoja(wb.create_sheet('Facturas anuladas'), 'Facturas anuladas', f'Período: {periodo}',
                 ['Fecha', 'Número', 'Detalle', 'Qué pasó', 'Total'],
                 [[f['fecha'].strftime('%d/%m/%Y') if f['fecha'] else '', f['numero'], f['detalle'],
                   f['motivo'], f['total']] for f in anuladas['filas']],
                 money_cols=[5])
    return _respuesta_excel(wb, _nombre_archivo(informe, 'xlsx'))


__all__ = ['respuesta_excel', 'respuesta_pdf']
