"""Comisiones por profesional sobre los servicios que cobró como vendedor.

Base = subtotal de cada línea de servicio de ventas completadas (descuento de línea incluido)
menos lo devuelto de esa línea. Las ventas anuladas no cuentan. Comisión = base × porcentaje
del profesional (`Usuario.comision_porcentaje`); sin porcentaje cargado la comisión es 0.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func

from app import db
from app.models import DetalleDevolucion, DetalleVenta, Devolucion, Usuario, Venta
from app.utils.helpers import utc_bounds_for_local_dates

CERO = Decimal('0')


def _lineas_de_servicio(desde: date, hasta: date):
    inicio, fin = utc_bounds_for_local_dates(desde, hasta)
    return (
        db.session.query(
            DetalleVenta.id_detalle_venta,
            Venta.id_usuario_vendedor,
            DetalleVenta.cantidad,
            DetalleVenta.subtotal,
        )
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.id_usuario_vendedor.isnot(None),
            DetalleVenta.id_servicio.isnot(None),
            Venta.fecha_venta >= inicio,
            Venta.fecha_venta < fin,
        )
        .all()
    )


def _devuelto_por_linea(ids_detalle) -> dict[int, Decimal]:
    if not ids_detalle:
        return {}
    filas = (
        db.session.query(DetalleDevolucion.id_detalle_venta_original, func.coalesce(func.sum(DetalleDevolucion.subtotal), 0))
        .join(Devolucion, Devolucion.id_devolucion == DetalleDevolucion.id_devolucion)
        .filter(
            Devolucion.estado != 'anulada',
            DetalleDevolucion.id_detalle_venta_original.in_(list(ids_detalle)),
        )
        .group_by(DetalleDevolucion.id_detalle_venta_original)
        .all()
    )
    return {int(fila[0]): Decimal(str(fila[1] or 0)) for fila in filas}


def calcular_comisiones(desde: date, hasta: date, profesionales: list | None = None) -> dict:
    """Comisiones del rango (fechas locales, ambas incluidas).

    `profesionales`: usuarios a listar aunque no hayan vendido; se suman los que vendieron.
    """
    lineas = _lineas_de_servicio(desde, hasta)
    devuelto = _devuelto_por_linea([linea[0] for linea in lineas])
    base_por_usuario = defaultdict(lambda: CERO)
    servicios_por_usuario = defaultdict(int)
    for id_detalle, id_vendedor, cantidad, subtotal in lineas:
        neto = Decimal(str(subtotal or 0)) - devuelto.get(int(id_detalle), CERO)
        if neto <= 0:
            continue
        base_por_usuario[int(id_vendedor)] += neto
        servicios_por_usuario[int(id_vendedor)] += int(cantidad or 0)

    usuarios = {int(usuario.id_usuario): usuario for usuario in (profesionales or [])}
    faltantes = set(base_por_usuario) - set(usuarios)
    if faltantes:
        for usuario in Usuario.query.filter(Usuario.id_usuario.in_(faltantes)).all():
            usuarios[int(usuario.id_usuario)] = usuario

    filas = []
    for id_usuario, usuario in usuarios.items():
        porcentaje = Decimal(str(usuario.comision_porcentaje)) if usuario.comision_porcentaje is not None else None
        base = base_por_usuario.get(id_usuario, CERO)
        comision = (base * porcentaje / Decimal('100')).quantize(Decimal('0.01')) if porcentaje is not None else CERO
        filas.append({
            'id': id_usuario,
            'nombre': usuario.nombre_completo or usuario.username,
            'porcentaje': float(porcentaje) if porcentaje is not None else None,
            'servicios': servicios_por_usuario.get(id_usuario, 0),
            'base': float(base),
            'comision': float(comision),
        })
    filas.sort(key=lambda fila: (-fila['comision'], -fila['base'], fila['nombre'].lower()))
    return {
        'desde': desde,
        'hasta': hasta,
        'filas': filas,
        'total_base': float(sum((Decimal(str(f['base'])) for f in filas), CERO)),
        'total_comision': float(sum((Decimal(str(f['comision'])) for f in filas), CERO)),
        'sin_porcentaje': [fila['nombre'] for fila in filas if fila['porcentaje'] is None and fila['base'] > 0],
    }
