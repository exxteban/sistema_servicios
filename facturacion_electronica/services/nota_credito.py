"""Lo que una nota de crédito toma de una devolución.

Una NC es la corrección fiscal de una factura ya emitida: sus líneas y sus
importes tienen que ser **los de la factura**, no los de cualquier otro lado.
Por eso el precio sale del detalle de venta original y no del precio guardado
en la devolución: si la línea tenía descuento, la factura cobró (y declaró el
IVA de) el precio con descuento, y acreditar más sería declarar de menos.

Cuando los dos números no coinciden se avisa en pantalla en vez de elegir uno
en silencio: el reembolso de caja y la NC estarían diciendo cosas distintas y
eso lo tiene que ver una persona.
"""
from types import SimpleNamespace

from facturacion_electronica import MOTIVO_NC_DEFECTO, MOTIVOS_NOTA_CREDITO

# IVA por defecto cuando no se puede recuperar el de la línea original. No
# debería pasar: sólo si la devolución perdió el enlace al detalle de venta.
IVA_POR_DEFECTO = 10


def motivo_valido(codigo):
    """Devuelve (codigo, descripcion) del catálogo, o (None, None) si no existe.

    La descripción no es texto libre: SIFEN sólo acepta las del catálogo
    TdDesMotEmi, así que se toma de la tabla y nunca del formulario.
    """
    try:
        codigo = int(codigo)
    except (TypeError, ValueError):
        return None, None
    for valor, descripcion in MOTIVOS_NOTA_CREDITO:
        if valor == codigo:
            return valor, descripcion
    return None, None


def motivo_o_defecto(codigo):
    valor, descripcion = motivo_valido(codigo)
    if valor is None:
        return motivo_valido(MOTIVO_NC_DEFECTO)
    return valor, descripcion


def _precio_unitario_facturado(detalle_original, detalle_devolucion):
    """Precio unitario neto tal como quedó en la factura."""
    if detalle_original is not None:
        cantidad = float(detalle_original.cantidad or 0)
        if cantidad:
            return float(detalle_original.subtotal or 0) / cantidad
    return float(detalle_devolucion.precio_unitario or 0)


def _iva_de_la_linea(detalle_original):
    if detalle_original is None:
        return IVA_POR_DEFECTO
    return int(detalle_original.porcentaje_iva or 0)


def lineas_de_devolucion(devolucion):
    """Líneas de la NC, con la forma que espera `data_builder.construir_items`.

    Se devuelven objetos livianos en vez de los `DetalleDevolucion` para no
    duplicar el mapeo fiscal: el mismo código que arma los ítems de la factura
    arma los de la nota de crédito.
    """
    lineas = []
    for detalle in devolucion.detalles:
        original = detalle.detalle_venta_original
        lineas.append(SimpleNamespace(
            producto=detalle.producto,
            servicio=getattr(detalle, 'servicio', None),
            id_producto=detalle.id_producto,
            cantidad=float(detalle.cantidad or 0),
            precio_unitario=_precio_unitario_facturado(original, detalle),
            # El descuento ya está dentro del precio facturado.
            descuento_linea=0,
            porcentaje_iva=_iva_de_la_linea(original),
        ))
    return lineas


def lineas_de_venta(venta):
    """Líneas de una NC que anula la factura entera, sin devolución detrás.

    Es el caso de la factura mal emitida: el cliente equivocado, el monto mal,
    la venta facturada dos veces. No vuelve mercadería y no se mueve stock;
    lo único que hay que corregir es el comprobante ante SIFEN.

    Se acredita **exactamente lo que declaró la factura**, así que el precio
    sale del subtotal de cada línea (que ya tiene el descuento adentro), por el
    mismo motivo que en una devolución: acreditar más sería declarar menos IVA
    del que se cobró.
    """
    lineas = []
    for detalle in venta.detalles:
        cantidad = float(detalle.cantidad or 0)
        if cantidad <= 0:
            continue
        lineas.append(SimpleNamespace(
            producto=detalle.producto,
            servicio=getattr(detalle, 'servicio', None),
            id_producto=detalle.id_producto,
            cantidad=cantidad,
            precio_unitario=float(detalle.subtotal or 0) / cantidad,
            descuento_linea=0,
            porcentaje_iva=int(detalle.porcentaje_iva or IVA_POR_DEFECTO),
        ))
    return lineas


def total_nota_credito(devolucion):
    return sum(l.cantidad * l.precio_unitario for l in lineas_de_devolucion(devolucion))


def advertencias(devolucion):
    """Diferencias que una persona tiene que mirar antes de emitir."""
    avisos = []
    reembolsado = float(devolucion.monto_total or 0)
    acreditado = total_nota_credito(devolucion)
    if abs(reembolsado - acreditado) >= 1:
        avisos.append(
            f'La devolución reembolsó {reembolsado:,.0f} Gs pero la factura había '
            f'facturado {acreditado:,.0f} Gs por esos ítems (la línea tenía descuento). '
            'La nota de crédito se emite por lo facturado: acreditar más sería '
            'declarar menos IVA del que se cobró.'
        )
    if any(d.detalle_venta_original is None for d in devolucion.detalles):
        avisos.append(
            'Algún ítem de la devolución no tiene enlace con la línea original de la '
            f'venta: se usa IVA {IVA_POR_DEFECTO}% y el precio guardado en la devolución. '
            'Revisá el importe antes de emitir.'
        )
    return avisos


def resumen_devoluciones(venta_id):
    """Devoluciones de la venta con su nota de crédito, para la pantalla.

    El import del modelo va adentro a propósito: el módulo de facturación no
    depende del de devoluciones más que acá.
    """
    from app.models.devolucion import Devolucion
    from facturacion_electronica import TIPO_NOTA_CREDITO
    from facturacion_electronica.models import DocumentoElectronico

    devoluciones = (
        Devolucion.query
        .filter_by(id_venta=venta_id)
        .order_by(Devolucion.id_devolucion.desc())
        .all()
    )
    if not devoluciones:
        return []

    notas = {
        nota.id_devolucion: nota
        for nota in DocumentoElectronico.query.filter(
            DocumentoElectronico.tipo_documento == TIPO_NOTA_CREDITO,
            DocumentoElectronico.id_devolucion.in_(
                [d.id_devolucion for d in devoluciones]
            ),
        ).order_by(DocumentoElectronico.id.asc()).all()
    }

    from facturacion_electronica.services.guarda import devolucion_anulada

    return [
        {
            'devolucion': devolucion,
            'total': total_nota_credito(devolucion),
            'reembolsado': float(devolucion.monto_total or 0),
            'nota': notas.get(devolucion.id_devolucion),
            'avisos': advertencias(devolucion),
            # La devolución anulada no se esconde (es historia de la venta),
            # pero no puede ofrecer el botón de emitir: acreditar una
            # devolución que se dio marcha atrás devuelve el IVA dos veces.
            'anulada': devolucion_anulada(devolucion),
        }
        for devolucion in devoluciones
    ]


__all__ = [
    'lineas_de_devolucion',
    'resumen_devoluciones',
    'total_nota_credito',
    'advertencias',
    'motivo_valido',
    'motivo_o_defecto',
]
