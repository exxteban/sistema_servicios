"""Que queda por devolver de una venta (portado del sistema padre).

La pantalla de devolucion usa esto para ofrecer el maximo por linea. Mismo
criterio que el endpoint `ventas.crear_devolucion`: las devoluciones anuladas
no cuentan, sus items vuelven a estar disponibles. Si la pantalla ofreciera
mas de lo que el endpoint acepta, el usuario carga la devolucion entera y
recien al confirmar se entera de que una linea no entraba.
"""
from sqlalchemy import func

from app import db
from app.models import DetalleDevolucion, Devolucion


def devueltos_por_detalle(venta):
    """{id_detalle_venta: (cantidad, subtotal) ya devueltos} de una venta."""
    filas = (
        db.session.query(
            DetalleDevolucion.id_detalle_venta_original,
            func.coalesce(func.sum(DetalleDevolucion.cantidad), 0),
            func.coalesce(func.sum(DetalleDevolucion.subtotal), 0),
        )
        .join(Devolucion, DetalleDevolucion.id_devolucion == Devolucion.id_devolucion)
        .filter(Devolucion.id_venta == venta.id_venta, Devolucion.estado != 'anulada')
        .group_by(DetalleDevolucion.id_detalle_venta_original)
        .all()
    )
    return {
        int(f[0]): (int(f[1] or 0), float(f[2] or 0))
        for f in filas if f and f[0] is not None
    }


def lineas_devolubles(venta):
    """Todas las lineas con lo que todavia se puede devolver.

    Las ya devueltas por completo tambien van (deshabilitadas en la pantalla):
    esconderlas haria parecer que la venta tenia menos items de los que tenia.
    """
    if venta is None:
        return []
    devueltos = devueltos_por_detalle(venta)
    lineas = []
    for detalle in venta.detalles:
        original = int(detalle.cantidad or 0)
        devuelto, subtotal_devuelto = devueltos.get(int(detalle.id_detalle_venta), (0, 0.0))
        disponible = max(original - devuelto, 0)
        # Lo que reembolsa cada unidad sale del subtotal que queda de la linea
        # (descuentos incluidos), igual que `calculate_refund_subtotal`.
        restante = float(detalle.subtotal or 0) - subtotal_devuelto
        lineas.append({
            'id_detalle_venta': int(detalle.id_detalle_venta),
            'nombre': detalle.item_nombre,
            'cantidad': original,
            'devuelto': devuelto,
            'disponible': disponible,
            'precio_unitario': restante / disponible if disponible else float(detalle.precio_unitario or 0),
        })
    return lineas
