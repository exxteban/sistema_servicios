"""Notas de crédito en papel: registrar el comprobante de una devolución y resumirlas.

Sólo sin facturación electrónica (con SIFEN la NC es un documento electrónico).
La devolución ya movió caja y stock; esto registra el número de la nota de
crédito que se le entregó al cliente, para que su IVA reste del débito.

El IVA sale de las líneas devueltas, cada una con el porcentaje de la línea de
la venta: así una devolución parcial de una venta con productos al 5% y al 10%
acredita lo que corresponde a cada uno. El monto es el que se devolvió.
"""
from app import db
from app.models import Devolucion, NotaCreditoPapel, Venta
from app.services.pos_numero_factura import facturacion_electronica_activa
from app.services.talonario_facturas import DIGITOS_NUMERO, parsear
from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local

PENDIENTES_A_MOSTRAR = 10


def totales_de_devolucion(devolucion):
    """Exentas, gravadas e IVA de lo devuelto, línea por línea."""
    t = {'exenta': 0.0, 'base5': 0.0, 'iva5': 0.0, 'base10': 0.0, 'iva10': 0.0, 'total': 0.0}
    for detalle in devolucion.detalles:
        monto = float(detalle.subtotal or 0)
        original = detalle.detalle_venta_original
        porcentaje = original.porcentaje_iva if original is not None else getattr(detalle.producto, 'porcentaje_iva', 10)
        if porcentaje == 10:
            t['iva10'] += monto / 11
            t['base10'] += monto - monto / 11
        elif porcentaje == 5:
            t['iva5'] += monto / 21
            t['base5'] += monto - monto / 21
        else:
            t['exenta'] += monto
        t['total'] += monto
    return t


def _formatear(numero):
    partes = parsear(numero)
    if partes is None:
        return numero
    establecimiento, punto, correlativo = partes
    return f'{establecimiento}-{punto}-{correlativo:0{DIGITOS_NUMERO}d}'


def registrar(devolucion, numero, timbrado, fecha, id_usuario=None):
    """Guarda, cambia o (con número vacío) borra la NC. Devuelve (nota, error)."""
    if facturacion_electronica_activa():
        return None, 'Con facturación electrónica la nota de crédito se emite desde SIFEN.'
    if devolucion.estado == 'anulada':
        return None, 'La devolución está anulada: no lleva nota de crédito.'
    venta = devolucion.venta
    if venta.estado == 'anulada':
        return None, 'La venta está anulada: no lleva nota de crédito.'
    if not (venta.numero_factura or '').strip():
        return None, 'La venta no tiene número de factura: la nota de crédito corrige una factura.'

    actual = devolucion.nota_credito_papel
    numero = (numero or '').strip()
    if not numero:
        if actual is not None:
            db.session.delete(actual)
        return None, None
    if len(numero) > 80:
        return None, 'El número de la nota de crédito es demasiado largo.'
    if fecha is None:
        return None, 'Falta la fecha de la nota de crédito.'
    numero = _formatear(numero)
    repetida = NotaCreditoPapel.query.filter(NotaCreditoPapel.numero == numero,
                                            NotaCreditoPapel.id_devolucion != devolucion.id_devolucion).first()
    if repetida is not None:
        return None, f'La nota de crédito {numero} ya está cargada en otra devolución.'

    nota = actual or NotaCreditoPapel(id_devolucion=devolucion.id_devolucion)
    nota.numero, nota.timbrado, nota.fecha = numero, (timbrado or '').strip()[:20] or None, fecha
    nota.id_usuario = id_usuario
    db.session.add(nota)
    return nota, None


def notas_del_mes(desde, hasta):
    """Una fila por NC con fecha en el mes (de devoluciones no anuladas)."""
    filas = (
        NotaCreditoPapel.query.join(Devolucion, Devolucion.id_devolucion == NotaCreditoPapel.id_devolucion)
        .join(Venta, Venta.id_venta == Devolucion.id_venta)
        .filter(NotaCreditoPapel.fecha >= desde, NotaCreditoPapel.fecha <= hasta,
                Devolucion.estado != 'anulada', Venta.estado != 'anulada')
        .order_by(NotaCreditoPapel.fecha.asc(), NotaCreditoPapel.id.asc())
        .all()
    )
    for nota in filas:
        devolucion = nota.devolucion
        yield {
            'numero': nota.numero,
            'timbrado': nota.timbrado or '',
            'fecha': nota.fecha,
            'id_venta': devolucion.id_venta,
            'id_cliente': devolucion.venta.id_cliente,
            'afecta': (devolucion.venta.numero_factura or '').strip(),
            'totales': totales_de_devolucion(devolucion),
        }


def devoluciones_sin_nota(desde, hasta):
    """Devoluciones del mes de ventas con factura que todavía no tienen NC cargada."""
    inicio, fin = utc_bounds_for_local_dates(desde, hasta)
    consulta = (
        Devolucion.query.join(Venta, Venta.id_venta == Devolucion.id_venta)
        .outerjoin(NotaCreditoPapel, NotaCreditoPapel.id_devolucion == Devolucion.id_devolucion)
        .filter(Devolucion.fecha_devolucion >= inicio, Devolucion.fecha_devolucion < fin,
                Devolucion.estado != 'anulada', Venta.estado != 'anulada', NotaCreditoPapel.id.is_(None),
                db.func.trim(db.func.coalesce(Venta.numero_factura, '')) != '')
        .order_by(Devolucion.fecha_devolucion.asc())
    )
    filas = consulta.all()
    return {
        'cantidad': len(filas),
        'monto': sum(float(d.monto_total or 0) for d in filas),
        'filas': [{'id_venta': d.id_venta, 'id_devolucion': d.id_devolucion,
                   'fecha': utc_naive_to_local(d.fecha_devolucion) if d.fecha_devolucion else None,
                   'factura': d.venta.numero_factura.strip(), 'monto': float(d.monto_total or 0)}
                  for d in filas[:PENDIENTES_A_MOSTRAR]],
    }


__all__ = ['devoluciones_sin_nota', 'notas_del_mes', 'registrar', 'totales_de_devolucion']
