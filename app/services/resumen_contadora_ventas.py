"""Débito fiscal sin facturación electrónica: las ventas con factura en papel.

Sin SIFEN no hay XML que leer, pero la venta guarda lo que hace falta: el
número de la factura (talonario preimpreso o autoimpresor, el campo "Nº
Factura" del POS) y su IVA. Lo que entra:

- **Ventas con factura:** completadas en el mes, con número cargado. Son el
  débito fiscal.
- **Ventas sin número:** no suman. Puede ser un ticket, o una factura a la que
  no se le cargó el número; se muestran aparte para que la persona decida.
- **Anuladas con número:** no suman, pero el/la contador/a las necesita para
  justificar el número que falta en el talonario.
- **Números repetidos:** dos ventas con el mismo número es un error de carga
  que se arrastra a la declaración. Es un pendiente.
- **Notas de crédito en papel:** restan del débito. Una devolución de una
  venta con factura sin su NC cargada es un pendiente: su IVA no se descuenta.
- **Talonario** (si hay alguno cargado): números que no caen en ningún
  timbrado vigente son pendiente; los saltos en la numeración, un aviso.

El IVA de la venta se guarda por ítem, antes del descuento. Si la venta tuvo
descuento se escala en proporción al total cobrado, que es lo que dice la
factura.
"""
from sqlalchemy import func

from app.models import Venta
from app.services.resumen_contadora import _sumar, _vacio
from app.services.notas_credito_papel import devoluciones_sin_nota, notas_del_mes
from app.services.talonario_facturas import resolvedor_de_timbrado, revision_del_mes
from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local

FILAS_ANULADAS = 50


def _numero():
    return func.trim(func.coalesce(Venta.numero_factura, ''))


def _del_mes(desde, hasta):
    inicio, fin = utc_bounds_for_local_dates(desde, hasta)
    return Venta.query.filter(Venta.fecha_venta >= inicio, Venta.fecha_venta < fin)


def totales_de_la_factura(subtotal, total, iva10, iva5, exenta):
    """Exentas, gravadas e IVA de lo que se facturó, con el descuento aplicado."""
    subtotal, total = float(subtotal or 0), float(total or 0)
    factor = (total / subtotal) if 0 <= total < subtotal else 1.0
    iva10, iva5 = float(iva10 or 0) * factor, float(iva5 or 0) * factor
    return {'exenta': float(exenta or 0) * factor, 'base5': iva5 * 20, 'iva5': iva5,
            'base10': iva10 * 10, 'iva10': iva10, 'total': total}


def iva_por_venta_con_factura(desde, hasta):
    """Una fila por venta con número de factura: lo que suma el débito fiscal."""
    resolver = resolvedor_de_timbrado()
    filas = (
        _del_mes(desde, hasta).filter(Venta.estado == 'completada', _numero() != '')
        .with_entities(Venta.id_venta, Venta.fecha_venta, Venta.numero_factura, Venta.id_cliente,
                       Venta.subtotal, Venta.total, Venta.total_iva_10, Venta.total_iva_5,
                       Venta.total_exenta, Venta.timbrado)
        .order_by(Venta.fecha_venta.asc(), Venta.id_venta.asc())
        .all()
    )
    for id_venta, fecha, numero, id_cliente, subtotal, total, iva10, iva5, exenta, timbrado in filas:
        local = utc_naive_to_local(fecha) if fecha else None
        numero = (numero or '').strip()
        yield {
            'id_venta': id_venta,
            'fecha': local,
            'numero': numero,
            'timbrado': (timbrado or '').strip() or (resolver(numero, local.date()) if local else None),
            'id_cliente': id_cliente,
            'totales': totales_de_la_factura(subtotal, total, iva10, iva5, exenta),
        }


def _repetidos(filas):
    """Números que aparecen en más de una venta del mismo timbrado, con las ventas de cada uno.

    Un timbrado nuevo vuelve a empezar la numeración: el mismo número con otro
    timbrado es otra factura. Una venta sin timbrado (no cae en ningún
    talonario) no se puede distinguir, así que choca con cualquiera de su número.
    """
    por_numero = {}
    for fila in filas:
        por_numero.setdefault(fila['numero'], []).append(fila)
    repetidos = []
    for numero, del_numero in sorted(por_numero.items()):
        if len(del_numero) < 2:
            continue
        if any(not f['timbrado'] for f in del_numero):
            repetidos.append({'numero': numero, 'ventas': [f['id_venta'] for f in del_numero]})
            continue
        por_timbrado = {}
        for fila in del_numero:
            por_timbrado.setdefault(fila['timbrado'], []).append(fila['id_venta'])
        repetidos.extend({'numero': numero, 'ventas': ventas}
                         for _, ventas in sorted(por_timbrado.items()) if len(ventas) > 1)
    return repetidos


def _sin_numero(desde, hasta):
    fila = (
        _del_mes(desde, hasta).filter(Venta.estado == 'completada', _numero() == '')
        .with_entities(func.count(Venta.id_venta), func.coalesce(func.sum(Venta.total), 0))
        .one()
    )
    return {'cantidad': int(fila[0] or 0), 'total': float(fila[1] or 0)}


def anuladas_con_numero(desde, hasta, limite=FILAS_ANULADAS):
    """Ventas anuladas del mes con número de factura; `limite=None` las trae todas."""
    consulta = _del_mes(desde, hasta).filter(Venta.estado == 'anulada', _numero() != '')
    filas = (
        consulta.with_entities(Venta.id_venta, Venta.fecha_venta, Venta.numero_factura, Venta.total)
        .order_by(Venta.fecha_venta.asc(), Venta.id_venta.asc())
    )
    if limite is not None:
        filas = filas.limit(limite)
    filas = filas.all()
    return {
        'cantidad': consulta.count(),
        'filas': [
            {'id_venta': id_venta, 'fecha': utc_naive_to_local(fecha) if fecha else None,
             'numero': (numero or '').strip(), 'total': float(total or 0)}
            for id_venta, fecha, numero, total in filas
        ],
    }


def ventas_con_factura_del_mes(desde, hasta):
    """Lo de las ventas en papel para el resumen: el bloque del cuadro y los avisos."""
    filas = list(iva_por_venta_con_factura(desde, hasta))
    ventas, notas = _vacio(), _vacio()
    for fila in filas:
        _sumar(ventas, fila['totales'])
    for nota in notas_del_mes(desde, hasta):
        _sumar(notas, nota['totales'])
    return {
        'ventas': ventas,
        'notas_credito': notas,
        'sin_nota_credito': devoluciones_sin_nota(desde, hasta),
        'repetidos': _repetidos(filas),
        'sin_numero': _sin_numero(desde, hasta),
        'anuladas': anuladas_con_numero(desde, hasta),
        'talonario': revision_del_mes(desde, hasta, filas),
    }


__all__ = ['anuladas_con_numero', 'iva_por_venta_con_factura','totales_de_la_factura', 'ventas_con_factura_del_mes']
