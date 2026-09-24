"""Arma el contexto del KuDE (representación gráfica del DE) de una venta.

El KuDE se imprime en lugar del ticket cuando la venta es facturada. Toma los
datos de la venta y de la config del emisor, más el CDC y el QR ya calculados
en el DocumentoElectronico.

Los importes de línea son los del DE, no los del detalle crudo: el descuento
global de la venta se prorratea sobre las líneas (igual que el XML y el POST
a la API). Sin eso el papel lista 100.000, un TOTAL de 90.000, y liquida IVA
sobre 100.000 mientras el documento declara 90.000.
"""
from facturacion_electronica import AMBIENTE_PRODUCCION, TIPO_NOTA_CREDITO
from facturacion_electronica.services.config_service import obtener_configuracion
from facturacion_electronica.services.data_builder import (
    _total_item,
    construir_items,
    redondeo_sedeco,
)
from facturacion_electronica.services.qr import qr_png_data_uri

# Consultor público de e-Kuatia. Son dos URLs distintas y el QR ya apunta a la
# que corresponde: si el pie dice siempre la de producción, quien tipee el CDC
# a mano durante las pruebas consulta el ambiente equivocado y no lo encuentra.
URL_CONSULTA_PRODUCCION = 'https://ekuatia.set.gov.py/consultas/'
URL_CONSULTA_TEST = 'https://ekuatia.set.gov.py/consultas-test/'


def _iva_de_linea(subtotal, porcentaje):
    """IVA contenido en un monto IVA-incluido (PYG no usa decimales)."""
    pct = int(porcentaje or 0)
    if pct == 10:
        return round(subtotal / 11)
    if pct == 5:
        return round(subtotal / 21)
    return 0


def _items_desde_venta(venta):
    """Ítems del KuDE con el mismo prorrateo que el documento electrónico."""
    return _items_kude(construir_items(list(venta.detalles), total_objetivo=venta.total))


def _items_kude(items_de):
    """Traduce los ítems del DE al formato que imprime el papel."""
    items = []
    for item in items_de:
        precio = float(item.get('precioUnitario') or 0)
        descuento = float(item.get('descuento') or 0)
        items.append({
            'codigo': (item.get('codigo') or '').strip(),
            'descripcion': (item.get('descripcion') or '').strip(),
            'cantidad': float(item.get('cantidad') or 0),
            'precio_unitario': precio - descuento,
            'iva_pct': int(item.get('iva') or 0),
            'subtotal': int(round(_total_item(item))),
        })
    return items


def _liquidacion_iva(items):
    exentas = gravado_5 = gravado_10 = iva_5 = iva_10 = 0
    for item in items:
        subtotal = float(item.get('subtotal') or 0)
        pct = int(item.get('iva_pct') or 0)
        if pct == 10:
            gravado_10 += subtotal
            iva_10 += _iva_de_linea(subtotal, 10)
        elif pct == 5:
            gravado_5 += subtotal
            iva_5 += _iva_de_linea(subtotal, 5)
        else:
            exentas += subtotal
    return {
        'exentas': exentas,
        'gravado_5': gravado_5,
        'gravado_10': gravado_10,
        'iva_5': iva_5,
        'iva_10': iva_10,
        'total_iva': iva_5 + iva_10,
    }


def _numero_formateado(documento):
    if not documento:
        return ''
    return f'{documento.establecimiento}-{documento.punto}-{documento.numero}'


def _lineas_nota_credito(documento):
    """Ítems de la NC: los de su devolución, con el precio que la factura cobró."""
    from app.models.devolucion import Devolucion
    from app import db
    from facturacion_electronica.services.nota_credito import lineas_de_devolucion

    devolucion = db.session.get(Devolucion, documento.id_devolucion)
    if devolucion is None:
        return []
    return _items_kude(construir_items(lineas_de_devolucion(devolucion)))


def construir_contexto_kude(venta, documento, paper_width_mm=80):
    """Devuelve el contexto para renderizar el template del KuDE.

    La nota de crédito imprime **sus** líneas y su total, no los de la venta:
    se acredita lo devuelto, que casi nunca es la factura entera. Sin esto el
    papel de la NC decía el total de la venta original y el cliente se llevaba
    un comprobante que contradice al documento que está en SIFEN.
    """
    config = obtener_configuracion()
    cliente = venta.cliente
    # getattr: el KuDE también se arma con documentos de prueba y con los DE
    # viejos, anteriores a las notas de crédito, que no tienen tipo cargado.
    es_nota_credito = getattr(documento, 'tipo_documento', None) == TIPO_NOTA_CREDITO

    if es_nota_credito:
        items = _lineas_nota_credito(documento)
        bruto = sum(item['subtotal'] for item in items)
    else:
        items = _items_desde_venta(venta)
        bruto = float(venta.total or 0)

    es_credito = (venta.tipo_venta or '').strip().lower() == 'credito'
    # El papel tiene que decir lo mismo que el DE: `xmlgen` baja el total al
    # múltiplo de 50 y declara la diferencia en dRedon. Si el KuDE imprimiera
    # el total crudo, el comprobante que se lleva el cliente no coincidiría
    # con el documento que quedó en SIFEN.
    total_redondeado, redondeo = redondeo_sedeco(bruto)

    # Identidad histórica del DE: reimprimir no debe leer el ambiente actual.
    es_produccion = (
        (documento.ambiente if documento and documento.ambiente else config.ambiente)
        == AMBIENTE_PRODUCCION
    )

    return {
        'config': config,
        'venta': venta,
        'documento': documento,
        'cliente': cliente,
        'items': items,
        'liquidacion': _liquidacion_iva(items),
        'subtotal': float(bruto),
        'redondeo': redondeo,
        'total': float(total_redondeado),
        'numero_documento': _numero_formateado(documento),
        'condicion_venta': 'Crédito' if es_credito else 'Contado',
        'es_nota_credito': es_nota_credito,
        'titulo_documento': (
            'NOTA DE CRÉDITO ELECTRÓNICA' if es_nota_credito else 'FACTURA ELECTRÓNICA'
        ),
        # La NC se emite el día que se emite, no el de la venta.
        'fecha_documento': (
            (getattr(documento, 'fecha_generado', None) if es_nota_credito else None)
            or venta.fecha_venta
        ),
        'motivo_nc': getattr(documento, 'nc_motivo_desc', None) if es_nota_credito else None,
        'factura_asociada': (
            getattr(documento, 'documento_asociado', None) if es_nota_credito else None
        ),
        'qr_img': qr_png_data_uri(documento.qr_url) if documento and documento.qr_url else None,
        # Igual que el ambiente: el timbrado impreso es el del DE, no el de hoy.
        # Si el documento es viejo y no lo tiene, se cae a la config (es lo
        # único que queda).
        'timbrado_numero': (
            (documento.timbrado if documento and documento.timbrado else None)
            or config.timbrado_numero or ''
        ),
        'timbrado_fecha_inicio': config.timbrado_fecha_inicio,
        'es_produccion': es_produccion,
        'url_consulta': URL_CONSULTA_PRODUCCION if es_produccion else URL_CONSULTA_TEST,
        'paper_width_mm': paper_width_mm if paper_width_mm in (58, 80) else 80,
    }


__all__ = ['construir_contexto_kude']
