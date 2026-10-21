"""Resumen del mes para el/la contador/a: IVA y lo que falta para cerrar.

Pensado para el profesional de afuera, no para el dueño: no muestra caja,
ganancia ni stock. Sólo lo que necesita para liquidar el IVA del mes y lo que
le impide hacerlo tranquila.

- **Débito fiscal:** el IVA de las facturas electrónicas aprobadas del mes,
  menos el de las notas de crédito aprobadas. Sale del XML que se mandó a
  SIFEN (lo que ella ve en Marangatu), no de la venta. Sin facturación
  electrónica, de las ventas con número de factura en papel
  (`resumen_contadora_ventas`).
- **Crédito fiscal:** el IVA de las compras **con número de factura** y de los
  gastos corrientes con su factura cargada (`gastos_credito_fiscal`). Sin
  comprobante ese IVA no se puede deducir, así que esas compras van aparte,
  como pendiente, con el IVA que se pierde si el papel no aparece.
- **Pendientes:** documentos rechazados, con error o sin respuesta de SIFEN
  del mes, y facturas cuyo XML no se pudo leer.

El saldo de acá es débito − crédito. El saldo a favor del mes anterior y las
retenciones no se pueden calcular: se cargan a mano y los resta
`contador_meses`.
"""
from datetime import date, timedelta

from sqlalchemy import func

from app import db
from app.models import Compra, Proveedor, Venta

FILAS_SIN_COMPROBANTE = 30
# La recepción de usados genera una Compra con su referencia interna (`US-…`)
# en `numero_factura` (ver `recepcion_usados`). No es una factura: se le
# compró a un particular, sin IVA. Va fuera de las dos listas.
PREFIJO_COMPRA_DE_USADO = 'US-'


def mes_vecino(primero, pasos):
    """El primero del mes `pasos` meses antes (negativo) o después."""
    indice = primero.year * 12 + (primero.month - 1) + pasos
    return date(indice // 12, indice % 12 + 1, 1)


def mes_por_defecto(hoy):
    """El mes anterior: es el que la contadora está liquidando."""
    primero = hoy.replace(day=1)
    return (primero - timedelta(days=1)).replace(day=1)


def rango_del_mes(primero):
    siguiente = (primero.replace(day=28) + timedelta(days=4)).replace(day=1)
    return primero, siguiente - timedelta(days=1)


def _vacio():
    return {'cantidad': 0, 'exenta': 0.0, 'base5': 0.0, 'iva5': 0.0,
            'base10': 0.0, 'iva10': 0.0, 'total': 0.0}


def _sumar(acumulado, totales):
    acumulado['cantidad'] += 1
    for clave in ('exenta', 'base5', 'iva5', 'base10', 'iva10', 'total'):
        acumulado[clave] += float(totales.get(clave) or 0)


def _iva(bloque):
    return bloque['iva5'] + bloque['iva10']


def _totales_de_la_venta(venta_total, iva10, iva5, exenta, monto=None, subtotal=None):
    """Estimación sin XML, aplicando el descuento de la factura.

    Con `monto` (lo que acreditó una NC) se escala en proporción al total de
    la venta: una devolución parcial acredita la parte que le toca.
    """
    from app.services.resumen_contadora_ventas import totales_de_la_factura

    venta_total = float(venta_total or 0)
    totales = totales_de_la_factura(subtotal, venta_total, iva10, iva5, exenta)
    if monto is None:
        return totales
    factor = float(monto) / venta_total if venta_total else 0.0
    return {clave: valor * factor for clave, valor in totales.items()}


def iva_por_documento(desde, hasta, ambiente):
    """Una fila por factura o NC aprobada del mes, con el IVA que suma al resumen.

    Es la fuente única de la fila del cuadro y de su detalle: si cada uno
    calculara por su lado, el modal podría no cerrar con el total de arriba.
    """
    from facturacion_electronica import TIPO_NOTA_CREDITO
    from facturacion_electronica.models import DocumentoElectronico
    from facturacion_electronica.services.listado_documentos import consulta_documentos
    from facturacion_electronica.services.totales_xml import totales_declarados
    from app.models.devolucion import Devolucion

    aprobados, fecha = consulta_documentos(desde, hasta, 'aprobado', ambiente=ambiente)
    filas = aprobados.with_entities(
        DocumentoElectronico.tipo_documento,
        func.coalesce(DocumentoElectronico.xml_qr, DocumentoElectronico.xml_firmado, DocumentoElectronico.xml),
        Venta.total, Venta.total_iva_10, Venta.total_iva_5, Venta.total_exenta, Venta.subtotal,
        DocumentoElectronico.id_devolucion,
        DocumentoElectronico.establecimiento, DocumentoElectronico.punto, DocumentoElectronico.numero,
        Venta.id_venta, Venta.id_cliente, fecha, DocumentoElectronico.id_documento_asociado,
    ).order_by(fecha.asc(), DocumentoElectronico.id.asc()).all()
    for (tipo, xml, total, iva10, iva5, exenta, subtotal, id_devolucion,
         establecimiento, punto, numero, id_venta, id_cliente, emitido, id_asociado) in filas:
        es_nc = tipo == TIPO_NOTA_CREDITO
        totales = totales_declarados(xml)
        estimada = totales is None
        if estimada and es_nc:
            # Lo que acreditó: la devolución, o la venta entera si es la
            # NC que anula la factura (igual que el listado de documentos).
            monto = total
            if id_devolucion:
                devolucion = db.session.get(Devolucion, id_devolucion)
                if devolucion is not None:
                    monto = devolucion.monto_total
            totales = _totales_de_la_venta(total, iva10, iva5, exenta, monto=monto or 0, subtotal=subtotal)
        elif estimada:
            totales = _totales_de_la_venta(total, iva10, iva5, exenta, subtotal=subtotal)
        yield {
            'es_nc': es_nc,
            'estimada': estimada,
            'totales': totales,
            'numero': f'{establecimiento}-{punto}-{numero}' if establecimiento and punto and numero else '',
            'id_venta': id_venta,
            'id_cliente': id_cliente,
            'fecha': emitido,
            'id_documento_asociado': id_asociado,
        }


def _documentos(desde, hasta, ambiente):
    """Facturas y NC del mes con IVA, más los conteos de lo que falta cerrar."""
    from facturacion_electronica import ESTADO_CANCELADO, ESTADO_INUTILIZADO
    from facturacion_electronica.models import DocumentoElectronico
    from facturacion_electronica.services.listado_documentos import consulta_documentos

    ventas, notas = _vacio(), _vacio()
    estimadas, nc_estimadas = 0, 0
    for fila in iva_por_documento(desde, hasta, ambiente):
        if fila['es_nc']:
            nc_estimadas += fila['estimada']
            _sumar(notas, fila['totales'])
        else:
            estimadas += fila['estimada']
            _sumar(ventas, fila['totales'])

    def contar(estado):
        consulta, _f = consulta_documentos(desde, hasta, estado, ambiente=ambiente)
        return consulta.count()

    def contar_estado(valor):
        consulta, _f = consulta_documentos(desde, hasta, ambiente=ambiente)
        return consulta.filter(DocumentoElectronico.estado == valor).count()

    return {
        'ventas': ventas,
        'notas_credito': notas,
        'ventas_estimadas': estimadas,
        'nc_estimadas': nc_estimadas,
        'rechazados': contar('atencion'),
        'sin_respuesta': contar('sin_enviar'),
        'canceladas': contar_estado(ESTADO_CANCELADO),
        'inutilizados': contar_estado(ESTADO_INUTILIZADO),
    }


def _compras_base(desde, hasta):
    return Compra.query.filter(
        Compra.estado != 'anulada',
        Compra.fecha_compra >= desde,
        Compra.fecha_compra <= hasta,
        ~func.coalesce(Compra.numero_factura, '').like(f'{PREFIJO_COMPRA_DE_USADO}%'),
    )


def _sin_numero():
    return func.coalesce(func.trim(Compra.numero_factura), '') == ''


def iva_por_compra(desde, hasta):
    """Una fila por compra con número de factura: lo que suma el crédito fiscal."""
    filas = (
        _compras_base(desde, hasta).filter(~_sin_numero())
        .outerjoin(Proveedor, Proveedor.id_proveedor == Compra.id_proveedor)
        .with_entities(Compra.id_compra, Compra.fecha_compra, Compra.numero_factura,
                       Proveedor.nombre, Proveedor.ruc,
                       Compra.total, Compra.total_iva_10, Compra.total_iva_5, Compra.timbrado)
        .order_by(Compra.fecha_compra.asc(), Compra.id_compra.asc())
        .all()
    )
    for id_compra, fecha, numero, nombre, ruc, total, iva10, iva5, timbrado in filas:
        iva10, iva5, total = float(iva10 or 0), float(iva5 or 0), float(total or 0)
        yield {
            'id_compra': id_compra, 'fecha': fecha, 'numero': (numero or '').strip(),
            'timbrado': (timbrado or '').strip(),
            'proveedor': (nombre or '').strip() or '—', 'ruc': (ruc or '').strip(),
            'totales': {'iva10': iva10, 'base10': iva10 * 10, 'iva5': iva5, 'base5': iva5 * 20,
                        'exenta': max(0.0, total - iva10 * 11 - iva5 * 21), 'total': total},
        }


def _compras(desde, hasta):
    """Con comprobante suman crédito fiscal; sin número de factura van aparte."""
    base = _compras_base(desde, hasta)
    sin_numero = _sin_numero()

    con = _vacio()
    for fila in iva_por_compra(desde, hasta):
        _sumar(con, fila['totales'])

    # Sin IVA no hay nada que deducir: una compra exenta sin número no es un
    # pendiente del IVA y sólo haría ruido.
    con_iva = (func.coalesce(Compra.total_iva_10, 0) + func.coalesce(Compra.total_iva_5, 0)) > 0
    faltantes = (
        base.filter(sin_numero, con_iva)
        .outerjoin(Proveedor, Proveedor.id_proveedor == Compra.id_proveedor)
        .with_entities(Compra.id_compra, Compra.fecha_compra, Proveedor.nombre,
                       Compra.total, Compra.total_iva_10, Compra.total_iva_5)
        .order_by(Compra.fecha_compra.asc(), Compra.id_compra.asc())
        .all()
    )
    filas = [
        {'id_compra': id_compra, 'fecha': fecha, 'proveedor': (nombre or '').strip() or '—',
         'total': float(total or 0), 'iva': float(iva10 or 0) + float(iva5 or 0)}
        for id_compra, fecha, nombre, total, iva10, iva5 in faltantes
    ]
    return con, {
        'cantidad': len(filas),
        'total': sum(f['total'] for f in filas),
        'iva_en_riesgo': sum(f['iva'] for f in filas),
        'filas': filas[:FILAS_SIN_COMPROBANTE],
    }


def anulados_del_mes(desde, hasta, ambiente, todas=False):
    """Facturas y NC del mes canceladas o con el número inutilizado.

    No suman IVA, pero el/la contador/a las necesita para justificar los
    saltos de la numeración y cruzar con Marangatu. Las anuladas con nota de
    crédito no están acá: siguen aprobadas y restan en la fila de NC.

    La pantalla muestra la primera página; el informe descargable (`todas`)
    las lleva completas, porque ahí no hay "ver más".
    """
    from facturacion_electronica.services.listado_documentos import listar_documentos

    pagina = listar_documentos(desde, hasta, estado='anulado', ambiente=ambiente)
    filas = list(pagina['filas'])
    numero = 1
    while todas and numero < pagina['paginas']:
        numero += 1
        filas += listar_documentos(desde, hasta, estado='anulado', pagina=numero, ambiente=ambiente)['filas']
    return {'cantidad': pagina['cantidad'], 'filas': filas}


def resumen_del_mes(primero, fe_activa, ambiente=None):
    """Todo lo de la pantalla para el mes que empieza en `primero`.

    Con facturación electrónica el débito sale de SIFEN (`documentos`); sin
    ella, de las ventas con número de factura en papel (`en_papel`). Nunca las
    dos: con SIFEN activo `numero_factura` registra facturas externas, y
    sumarlas duplicaría ventas.
    """
    from app.services.gastos_credito_fiscal import gastos_del_mes, pagos_sin_factura
    from app.services.resumen_contadora_controles import controles_del_mes
    from app.services.resumen_contadora_ventas import ventas_con_factura_del_mes

    desde, hasta = rango_del_mes(primero)
    compras, sin_comprobante = _compras(desde, hasta)
    documentos = _documentos(desde, hasta, ambiente) if fe_activa else None
    anulados = anulados_del_mes(desde, hasta, ambiente) if fe_activa else None
    en_papel = None if fe_activa else ventas_con_factura_del_mes(desde, hasta)

    debito = 0.0
    if documentos:
        debito = _iva(documentos['ventas']) - _iva(documentos['notas_credito'])
    elif en_papel:
        debito = _iva(en_papel['ventas']) - _iva(en_papel['notas_credito'])
    gastos = _vacio()
    for fila in gastos_del_mes(desde, hasta):
        _sumar(gastos, fila['totales'])
    credito = _iva(compras) + _iva(gastos)

    controles = controles_del_mes(desde, hasta, fe_activa)
    pendientes = sin_comprobante['cantidad'] + controles['cantidad']
    if documentos:
        pendientes += (documentos['rechazados'] + documentos['sin_respuesta']
                       + documentos['ventas_estimadas'] + documentos['nc_estimadas'])
    elif en_papel:
        pendientes += len(en_papel['repetidos']) + en_papel['sin_nota_credito']['cantidad']
        if en_papel['talonario']:
            pendientes += len(en_papel['talonario']['fuera_de_talonario'])

    return {
        'desde': desde,
        'hasta': hasta,
        'fe_activa': bool(fe_activa),
        'ambiente': ambiente,
        'documentos': documentos,
        'anulados': anulados,
        'en_papel': en_papel,
        'controles': controles,
        'compras': compras,
        'gastos': gastos,
        'gastos_sin_factura': pagos_sin_factura(desde, hasta),
        'sin_comprobante': sin_comprobante,
        'debito': debito,
        'credito': credito,
        'saldo': debito - credito,
        'pendientes': pendientes,
    }


def parse_mes(texto):
    """'2026-09' → date(2026, 9, 1); None si no se entiende."""
    try:
        anio, mes = (int(p) for p in (texto or '').split('-')[:2])
        return date(anio, mes, 1)
    except (TypeError, ValueError):
        return None


__all__ = ['anulados_del_mes', 'iva_por_compra','iva_por_documento', 'mes_por_defecto', 'mes_vecino', 'parse_mes', 'rango_del_mes', 'resumen_del_mes']
