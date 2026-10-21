"""Detalle de cada fila del cuadro de IVA del resumen para el/la contador/a.

La fila dice "33 facturas, IVA ₲ 564.218"; el detalle muestra cuáles son y
cuánto aporta cada una, para cruzarlas con Marangatu de a una. Sale de los
mismos generadores que la fila (`iva_por_documento`, `iva_por_compra`), así
que el total del detalle cierra siempre con el de arriba.
"""
from app.models import Cliente
from app.services.resumen_contadora import iva_por_compra, iva_por_documento, rango_del_mes
from app.services.gastos_credito_fiscal import gastos_del_mes
from app.services.notas_credito_papel import notas_del_mes
from app.services.resumen_contadora_ventas import iva_por_venta_con_factura
from app.utils.helpers import utc_naive_to_local

FILAS = {
    'ventas': 'Facturas electrónicas aprobadas',
    'notas': 'Notas de crédito aprobadas',
    'compras': 'Compras con número de factura',
    'ventas_factura': 'Ventas con número de factura',
    'notas_papel': 'Notas de crédito',
    'gastos': 'Gastos con factura',
}
# Las que salen de SIFEN sólo existen con facturación electrónica activa; la
# de ventas en papel, sólo sin ella. Compras, siempre.
FILAS_SIFEN = ('ventas', 'notas')
FILAS_SIN_SIFEN = ('ventas_factura', 'notas_papel')
CLAVES_MONTO = ('exenta', 'base5', 'iva5', 'base10', 'iva10', 'total')


def _clientes(ids):
    ids = {i for i in ids if i}
    if not ids:
        return {}
    filas = Cliente.query.with_entities(Cliente.id_cliente, Cliente.nombre, Cliente.ruc_ci) \
        .filter(Cliente.id_cliente.in_(ids)).all()
    return {i: ((nombre or '').strip() or '—', (ruc or '').strip()) for i, nombre, ruc in filas}


def _numeros_asociados(ids):
    """Número de la factura que corrige cada NC."""
    from facturacion_electronica.models import DocumentoElectronico

    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {d.id: d.numero_formateado for d in DocumentoElectronico.query.filter(DocumentoElectronico.id.in_(ids))}


def _documentos(desde, hasta, ambiente, notas):
    docs = [d for d in iva_por_documento(desde, hasta, ambiente) if d['es_nc'] == notas]
    clientes = _clientes(d['id_cliente'] for d in docs)
    asociados = _numeros_asociados(d['id_documento_asociado'] for d in docs) if notas else {}
    filas = []
    for d in docs:
        nombre, ruc = clientes.get(d['id_cliente'], ('—', ''))
        filas.append({
            'fecha': utc_naive_to_local(d['fecha']) if d['fecha'] else None,
            'numero': d['numero'] or '—',
            'nombre': nombre,
            'ruc': ruc,
            'afecta': asociados.get(d['id_documento_asociado'], '') if notas else '',
            'estimada': d['estimada'],
            'id_venta': d['id_venta'],
            'id_compra': None,
            **{k: float(d['totales'].get(k) or 0) for k in CLAVES_MONTO},
        })
    return filas


def _en_papel(documentos):
    """Ventas o notas de crédito en papel con el formato de fila del detalle."""
    documentos = list(documentos)
    clientes = _clientes(v['id_cliente'] for v in documentos)
    filas = []
    for v in documentos:
        nombre, ruc = clientes.get(v['id_cliente'], ('—', ''))
        filas.append({
            'fecha': v['fecha'],
            'numero': v['numero'],
            'timbrado': v['timbrado'] or '',
            'nombre': nombre,
            'ruc': ruc,
            'afecta': v.get('afecta', ''),
            'estimada': False,
            'id_venta': v['id_venta'],
            'id_compra': None,
            **{k: float(v['totales'].get(k) or 0) for k in CLAVES_MONTO},
        })
    return filas


def _compras(desde, hasta):
    return [
        {
            'fecha': c['fecha'],
            'numero': c['numero'],
            'timbrado': c['timbrado'],
            'nombre': c['proveedor'],
            'ruc': c['ruc'],
            'afecta': '',
            'estimada': False,
            'id_venta': None,
            'id_compra': c['id_compra'],
            **{k: float(c['totales'].get(k) or 0) for k in CLAVES_MONTO},
        }
        for c in iva_por_compra(desde, hasta)
    ]


def _gastos(desde, hasta):
    return [
        {
            'fecha': g['fecha'], 'numero': g['numero'], 'timbrado': g['timbrado'],
            'nombre': g['proveedor'], 'ruc': g['ruc'], 'afecta': '', 'estimada': False,
            'id_venta': None, 'id_compra': None, 'id_gasto': g['id_gasto_corriente'],
            **{k: float(g['totales'].get(k) or 0) for k in CLAVES_MONTO},
        }
        for g in gastos_del_mes(desde, hasta)
    ]


def detalle_fila(primero, fila, ambiente):
    """Las filas que suman `fila` en el mes de `primero`. None si `fila` no existe."""
    if fila not in FILAS:
        return None
    desde, hasta = rango_del_mes(primero)
    if fila == 'compras':
        filas = _compras(desde, hasta)
    elif fila == 'ventas_factura':
        filas = _en_papel(iva_por_venta_con_factura(desde, hasta))
    elif fila == 'notas_papel':
        filas = _en_papel(notas_del_mes(desde, hasta))
    elif fila == 'gastos':
        filas = _gastos(desde, hasta)
    else:
        filas = _documentos(desde, hasta, ambiente, notas=(fila == 'notas'))
    totales = {k: sum(f[k] for f in filas) for k in CLAVES_MONTO}
    return {
        'clave': fila,
        'titulo': FILAS[fila],
        'desde': desde,
        'hasta': hasta,
        'es_compra': fila in ('compras', 'gastos'),
        'es_nota': fila in ('notas', 'notas_papel'),
        # En papel el/la contador/a carga el timbrado de cada comprobante.
        'con_timbrado': fila in ('compras', 'gastos', 'ventas_factura', 'notas_papel'),
        'filas': filas,
        'totales': totales,
    }


def tabla(detalle):
    """Encabezados, filas (con la de total) y columnas de montos del detalle.

    La van a usar el .xlsx de una fila y el Excel completo del mes (todavía
    no portados de sistema_silvio_cel), para que las columnas sean las mismas.
    """
    quien = 'Proveedor' if detalle['es_compra'] else 'Cliente'
    headers = ['Fecha', 'Número'] + (['Timbrado'] if detalle['con_timbrado'] else []) + [quien, 'RUC']
    if detalle['es_nota']:
        headers.append('Factura que afecta')
    headers += ['Exentas', 'Gravadas 5%', 'IVA 5%', 'Gravadas 10%', 'IVA 10%', 'Total']
    filas = []
    for f in detalle['filas']:
        fila = [f['fecha'].strftime('%d/%m/%Y') if f['fecha'] else '', f['numero']]
        fila += [f['timbrado']] if detalle['con_timbrado'] else []
        fila += [f['nombre'], f['ruc']]
        if detalle['es_nota']:
            fila.append(f['afecta'])
        # Conservar la precisión para que SUMA en Excel cierre con el resumen.
        # El formato de celda se encarga de mostrar los guaraníes.
        fila += [f[k] for k in CLAVES_MONTO]
        filas.append(fila)
    total = ['Total'] + [''] * (len(headers) - len(CLAVES_MONTO) - 1)
    filas.append(total + [detalle['totales'][k] for k in CLAVES_MONTO])
    primera_monto = len(headers) - len(CLAVES_MONTO) + 1
    return headers, filas, range(primera_monto, len(headers) + 1)


__all__ = ['FILAS', 'FILAS_SIFEN', 'FILAS_SIN_SIFEN', 'detalle_fila', 'tabla']
