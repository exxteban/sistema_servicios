"""Qué queda por devolver de una venta.

Vive acá y no dentro de la ruta para que la **pantalla** y el **endpoint** no
se desincronicen: si la pantalla ofreciera devolver más de lo que el endpoint
acepta, el usuario carga la devolución entera y recién al confirmar se entera
de que una línea no entraba. Y al revés es peor: una pantalla más permisiva que
la validación es la forma de devolver dos veces el mismo ítem.

Portado de sistema_silvio_cel. Lo propio de este sistema: puede correr con una
moneda con centavos (R$ en Brasil). El reparto de la factura electrónica
redondea cada línea a guaraníes enteros, así que sólo se usa con moneda sin
decimales; con centavos el descuento global se reparte en proporción y el
redondeo es a los decimales de la moneda.
"""
from decimal import Decimal

from sqlalchemy import func

from app import db
from app.models import DetalleDevolucion, Devolucion


def devueltos_por_detalle(venta, detalle_ids=None):
    """{id_detalle_venta: cantidad ya devuelta} de una venta.

    Las devoluciones anuladas no cuentan: sus ítems volvieron a estar
    disponibles.
    """
    query = (
        db.session.query(
            DetalleDevolucion.id_detalle_venta_original,
            func.coalesce(func.sum(DetalleDevolucion.cantidad), 0),
        )
        .join(Devolucion, DetalleDevolucion.id_devolucion == Devolucion.id_devolucion)
        .filter(
            Devolucion.id_venta == venta.id_venta,
            Devolucion.estado != 'anulada',
        )
    )
    if detalle_ids is not None:
        query = query.filter(
            DetalleDevolucion.id_detalle_venta_original.in_(list(detalle_ids))
        )

    filas = query.group_by(DetalleDevolucion.id_detalle_venta_original).all()
    return {
        int(fila[0]): Decimal(str(fila[1] or 0))
        for fila in filas
        if fila and fila[0] is not None
    }


def precios_reembolsables(venta):
    """{id_detalle_venta: precio unitario cobrado} de toda la venta.

    Es el mismo precio que declaró la factura (`precios_facturados`): la
    devolución y su nota de crédito no pueden diferir ni por el redondeo del
    reparto del descuento global. La excepción es la venta con descuento total:
    el reparto la deja sin tocar (no hay nada que prorratear) y se reembolsaría
    un precio que nadie pagó.
    """
    from facturacion_electronica.services.nota_credito import precios_facturados

    if float(venta.total or 0) <= 0:
        return {detalle.id_detalle_venta: 0.0 for detalle in venta.detalles}
    if _decimales_moneda() > 0:
        return _precios_con_descuento_proporcional(venta)
    return precios_facturados(venta)


def _decimales_moneda():
    from app.utils.helpers import config_moneda

    return int(config_moneda().get('decimales') or 0)


def _precios_con_descuento_proporcional(venta):
    """Precio neto por unidad con el descuento global repartido sin redondear."""
    detalles = list(venta.detalles)
    bruto = sum(float(d.subtotal or 0) for d in detalles)
    total = float(venta.total or 0)
    factor = total / bruto if 0 < total < bruto else 1.0
    precios = {}
    for detalle in detalles:
        cantidad = float(detalle.cantidad or 0)
        neto = float(detalle.subtotal or 0) / cantidad if cantidad else float(detalle.precio_unitario or 0)
        precios[detalle.id_detalle_venta] = neto * factor
    return precios


def precio_reembolsable(venta, detalle, precios=None):
    """Precio cobrado por unidad, con descuentos de línea y globales.

    `precios` (de `precios_reembolsables`) evita recalcular la venta entera
    por cada línea cuando se recorren varias.
    """
    if precios is None:
        precios = precios_reembolsables(venta)
    precio = precios.get(detalle.id_detalle_venta)
    if precio is None:
        cantidad = float(detalle.cantidad or 0)
        precio = float(detalle.subtotal or 0) / cantidad if cantidad else float(detalle.precio_unitario or 0)
    return Decimal(str(precio))


def monto_reembolsable(precio, cantidad, ya_devuelta=0):
    """Redondeo acumulado: fraccionar una devolución no aumenta el reembolso.

    A los decimales de la moneda (guaraníes enteros, como las líneas de la
    factura): devolver una línea entera, de una vez o en partes, reembolsa
    exactamente lo facturado.
    """
    paso = Decimal(1).scaleb(-_decimales_moneda())
    anterior = precio * Decimal(str(ya_devuelta))
    actual = anterior + precio * Decimal(str(cantidad))
    return actual.quantize(paso) - anterior.quantize(paso)


def lineas_devolubles(venta):
    """Líneas de la venta con lo que todavía se puede devolver, para la pantalla.

    Se devuelven **todas** las líneas, incluso las ya devueltas por completo:
    esconderlas haría parecer que la venta tenía menos ítems de los que tenía.
    La pantalla las muestra deshabilitadas.
    """
    if venta is None:
        return []

    devueltos = devueltos_por_detalle(venta)
    precios = precios_reembolsables(venta)
    lineas = []
    for detalle in venta.detalles:
        # En este sistema las cantidades vendidas son enteras (también los servicios).
        original = int(detalle.cantidad or 0)
        devuelto = int(devueltos.get(int(detalle.id_detalle_venta), Decimal('0')))
        disponible = original - devuelto
        lineas.append({
            'id_detalle_venta': int(detalle.id_detalle_venta),
            'nombre': detalle.item_nombre,
            'cantidad': original,
            'devuelto': devuelto,
            'disponible': disponible if disponible > 0 else 0,
            'precio_unitario': float(precio_reembolsable(venta, detalle, precios)),
        })
    return lineas


def hay_algo_para_devolver(venta):
    return any(linea['disponible'] > 0 for linea in lineas_devolubles(venta))


__all__ = ['devueltos_por_detalle', 'lineas_devolubles', 'hay_algo_para_devolver',
           'precios_reembolsables', 'precio_reembolsable', 'monto_reembolsable']
