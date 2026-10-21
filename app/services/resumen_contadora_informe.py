"""Informe del mes para el/la contador/a: lo mismo que la pantalla, para descargar.

Junta en un solo lugar el resumen de IVA, el saldo y el cierre del mes, las
observaciones en lenguaje claro y los anexos con cada comprobante. Lo usan el
PDF y el Excel completo. No calcula nada propio: sale de `resumen_del_mes`,
`estado_del_mes` y `detalle_fila`, así que los números son los de la pantalla.
"""
from app.models import Configuracion
from app.services.contador_meses import estado_del_mes
from app.services.resumen_contadora import resumen_del_mes
from app.services.resumen_contadora_detalle import detalle_fila
from app.utils.helpers import now_local

VENTAS_SIN_NUMERO_EN_ESTE_SISTEMA = (
    'Las ventas todavía no registran el número de la factura en papel: el débito fiscal '
    'de este informe no incluye las ventas del mes. El crédito fiscal y los controles están completos.')


def _gs(valor):
    # "Gs." y no "₲": la fuente del PDF no tiene el signo del guaraní.
    return f'Gs. {float(valor or 0):,.0f}'.replace(',', '.')


def _lista(textos, limite=10):
    textos = [t for t in textos if t]
    resto = len(textos) - limite
    return ', '.join(textos[:limite]) + (f' y {resto} más' if resto > 0 else '')


def _empresa():
    return {
        'nombre': (Configuracion.obtener('nombre_empresa', '') or '').strip(),
        'ruc': (Configuracion.obtener('ruc_empresa', '') or '').strip(),
    }


def _observaciones(r, cierre):
    """Lo mismo que el bloque de pendientes de la pantalla, en frases."""
    pendientes, avisos = [], []
    cambio = cierre['cambio_desde_presentado']
    if cambio:
        pendientes.append(
            f"Cambió después de presentado: débito {_gs(cambio['debito_antes'])} → {_gs(r['debito'])}, "
            f"crédito {_gs(cambio['credito_antes'])} → {_gs(r['credito'])}. Revisar si hay que rectificar.")
    docs, papel, c = r['documentos'], r['en_papel'], r['controles']
    pendientes.extend(c['conciliacion']['filas'])
    if c['conciliacion']['cantidad'] > len(c['conciliacion']['filas']):
        pendientes.append('Hay más avisos de conciliación: revisá los comprobantes de los anexos.')
    if docs:
        if docs['rechazados']:
            pendientes.append(f"{docs['rechazados']} documento(s) electrónico(s) rechazado(s) o con error: no suman hasta que SIFEN los apruebe.")
        if docs['sin_respuesta']:
            pendientes.append(f"{docs['sin_respuesta']} documento(s) electrónico(s) sin respuesta de SIFEN.")
        if docs['ventas_estimadas'] or docs['nc_estimadas']:
            pendientes.append(f"{docs['ventas_estimadas'] + docs['nc_estimadas']} documento(s) sin copia local del XML: "
                              'su IVA se calculó con la venta y puede diferir en unos guaraníes.')
    if papel:
        # En este sistema el POS todavía no carga el número de factura en papel
        # (llega con los talonarios): sin esta aclaración un débito de Gs. 0 en
        # el informe se lee como "no hubo ventas".
        avisos.append(VENTAS_SIN_NUMERO_EN_ESTE_SISTEMA)
        for rep in papel['repetidos']:
            pendientes.append(f"El número de factura {rep['numero']} está cargado en {len(rep['ventas'])} ventas: todas suman al débito.")
        sin_nc = papel['sin_nota_credito']
        if sin_nc['cantidad']:
            pendientes.append(f"{sin_nc['cantidad']} devolución(es) de ventas con factura por {_gs(sin_nc['monto'])} sin nota de crédito: "
                              f"su IVA no se descuenta. Facturas: {_lista([f['factura'] for f in sin_nc['filas']])}.")
        talonario = papel['talonario']
        if talonario and talonario['fuera_de_talonario']:
            fuera = talonario['fuera_de_talonario']
            pendientes.append(f"{len(fuera)} venta(s) con un número que no corresponde a ningún talonario vigente: "
                              f"{_lista([f['numero'] for f in fuera])}.")
        if talonario and talonario['saltos']['cantidad']:
            saltos = talonario['saltos']
            resto = saltos['cantidad'] - len(saltos['numeros'])
            avisos.append(f"Saltos en la numeración: {saltos['cantidad']} número(s) sin venta "
                          f"({_lista(saltos['numeros'])}{f' y {resto} más' if resto > 0 else ''}).")
        if papel['sin_numero']['cantidad']:
            avisos.append(f"{papel['sin_numero']['cantidad']} venta(s) sin número de factura por {_gs(papel['sin_numero']['total'])}: no suman al débito.")
    if c['compras_sin_timbrado']['cantidad']:
        pendientes.append(f"{c['compras_sin_timbrado']['cantidad']} compra(s) con factura sin timbrado: "
                          f"{_lista([f['numero'] for f in c['compras_sin_timbrado']['filas']])}.")
    if c['iva_no_cierra']['cantidad']:
        pendientes.append(f"{c['iva_no_cierra']['cantidad']} compra(s) con más IVA del que el total permite: "
                          f"{_lista([f['numero'] for f in c['iva_no_cierra']['filas']])}.")
    if c['ruc_invalidos']['cantidad']:
        rucs = [f"{f['nombre']} ({f['ruc']})" for f in c['ruc_invalidos']['filas']]
        pendientes.append(f"{c['ruc_invalidos']['cantidad']} RUC con el dígito verificador mal: {_lista(rucs)}.")
    sin_comprobante = r['sin_comprobante']
    if sin_comprobante['cantidad']:
        pendientes.append(f"{sin_comprobante['cantidad']} compra(s) sin número de factura por {_gs(sin_comprobante['total'])}: "
                          f"{_gs(sin_comprobante['iva_en_riesgo'])} de IVA que no se puede deducir sin el comprobante.")
    if r['gastos_sin_factura']['cantidad']:
        avisos.append(f"{r['gastos_sin_factura']['cantidad']} pago(s) de gastos corrientes por "
                      f"{_gs(r['gastos_sin_factura']['total'])} sin factura cargada: no suman al crédito.")
    return pendientes, avisos


def _anuladas(r):
    """Todas las anuladas del mes: la pantalla corta en una página, el informe no."""
    from app.services.resumen_contadora import anulados_del_mes
    from app.services.resumen_contadora_ventas import anuladas_con_numero

    if r['anulados'] is not None:
        anulados = anulados_del_mes(r['desde'], r['hasta'], r['ambiente'], todas=True)
        filas = [{'fecha': f['fecha'], 'numero': f['numero'], 'detalle': f'{f["tipo"]} · {f["cliente"]}',
                  'motivo': 'Cancelada en SIFEN' if f['estado'] == 'cancelado' else 'Número inutilizado',
                  'total': f['total']} for f in anulados['filas']]
        return {'cantidad': anulados['cantidad'], 'filas': filas}
    if r['en_papel']:
        anuladas = anuladas_con_numero(r['desde'], r['hasta'], limite=None)
        filas = [{'fecha': f['fecha'], 'numero': f['numero'], 'detalle': f'Venta #{f["id_venta"]}',
                  'motivo': 'Venta anulada', 'total': f['total']} for f in anuladas['filas']]
        return {'cantidad': anuladas['cantidad'], 'filas': filas}
    return {'cantidad': 0, 'filas': []}


def _cuadro(r):
    """Las filas del cuadro de IVA, con el lado (débito o crédito) y si restan."""
    filas = []
    if r['documentos']:
        filas += [('debito', 'Facturas electrónicas aprobadas', r['documentos']['ventas'], False),
                  ('debito', 'Notas de crédito aprobadas', r['documentos']['notas_credito'], True)]
    elif r['en_papel']:
        filas += [('debito', 'Ventas con número de factura', r['en_papel']['ventas'], False),
                  ('debito', 'Notas de crédito', r['en_papel']['notas_credito'], True)]
    filas += [('credito', 'Compras con número de factura', r['compras'], False),
              ('credito', 'Gastos con factura', r['gastos'], False)]
    return [{'lado': lado, 'concepto': c, 'b': b, 'resta': resta} for lado, c, b, resta in filas]


def informe_del_mes(primero, fe_activa, ambiente=None):
    r = resumen_del_mes(primero, fe_activa, ambiente)
    cierre = estado_del_mes(primero, r['debito'], r['credito'])
    claves = (['ventas', 'notas'] if fe_activa else ['ventas_factura', 'notas_papel']) + ['compras', 'gastos']
    anexos = [detalle_fila(primero, clave, ambiente) for clave in claves]
    pendientes, avisos = _observaciones(r, cierre)
    return {
        'empresa': _empresa(),
        'primero': primero,
        # Hora del negocio, no la del servidor (que corre en UTC).
        'generado': now_local(),
        'resumen': r,
        'hay_debito': bool(r['documentos'] or r['en_papel']),
        'cuadro': _cuadro(r),
        'cierre': cierre,
        'anexos': anexos,
        'pendientes': pendientes,
        'avisos': avisos,
        'anuladas': _anuladas(r),
    }


__all__ = ['informe_del_mes']
