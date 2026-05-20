from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db


def _money(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def obtener_resumen_anulaciones_ventas_sesion(sesion, efectivo_id=None):
    from app.models import Auditoria, MovimientoCaja, PagoVenta, Venta

    start_ts = sesion.fecha_apertura or datetime.min
    end_ts = sesion.fecha_cierre or datetime.utcnow()

    auditorias_rows = (
        db.session.query(Auditoria.referencia_id, Auditoria.fecha_accion)
        .join(Venta, Venta.id_venta == Auditoria.referencia_id)
        .filter(
            Venta.id_sesion_caja == sesion.id_sesion,
            Auditoria.accion == 'anular_venta',
            Auditoria.modulo == 'ventas',
            Auditoria.referencia_tipo == 'venta',
            Auditoria.referencia_id.isnot(None),
            Auditoria.fecha_accion >= start_ts,
            Auditoria.fecha_accion < end_ts,
        )
        .order_by(Auditoria.fecha_accion.asc(), Auditoria.id_auditoria.asc())
        .all()
    )

    fecha_por_venta = {}
    venta_ids_auditadas = []
    for referencia_id, fecha_accion in auditorias_rows:
        try:
            venta_id = int(referencia_id)
        except Exception:
            continue
        if venta_id in fecha_por_venta:
            continue
        fecha_por_venta[venta_id] = fecha_accion
        venta_ids_auditadas.append(venta_id)

    movimientos_efectivo_rows_raw = (
        db.session.query(
            MovimientoCaja.referencia_id.label('id_venta'),
            func.sum(MovimientoCaja.monto).label('total'),
            func.min(MovimientoCaja.fecha_movimiento).label('fecha_movimiento'),
        )
        .filter(
            MovimientoCaja.id_sesion_caja == sesion.id_sesion,
            MovimientoCaja.tipo == 'egreso',
            MovimientoCaja.referencia_tipo == 'anulacion_venta',
            MovimientoCaja.referencia_id.isnot(None),
        )
        .group_by(MovimientoCaja.referencia_id)
        .order_by(func.min(MovimientoCaja.fecha_movimiento).asc(), MovimientoCaja.referencia_id.asc())
        .all()
    )

    movimientos_efectivo_rows = []
    movimientos_efectivo_por_venta = {}
    venta_ids_mov_efectivo = []
    for row in movimientos_efectivo_rows_raw:
        try:
            venta_id = int(row.id_venta)
        except Exception:
            continue
        total = _money(row.total)
        movimientos_efectivo_rows.append(
            {
                'id_venta': venta_id,
                'total': total,
                'fecha': row.fecha_movimiento,
            }
        )
        movimientos_efectivo_por_venta[venta_id] = total
        venta_ids_mov_efectivo.append(venta_id)
        if venta_id not in fecha_por_venta:
            fecha_por_venta[venta_id] = row.fecha_movimiento

    pagos_rows = []
    esperado_por_metodo = {}
    if venta_ids_auditadas:
        pagos_rows = (
            db.session.query(
                PagoVenta.id_venta,
                PagoVenta.id_metodo_pago,
                func.sum(PagoVenta.monto).label('total'),
            )
            .filter(PagoVenta.id_venta.in_(sorted(set(venta_ids_auditadas))))
            .group_by(PagoVenta.id_venta, PagoVenta.id_metodo_pago)
            .order_by(PagoVenta.id_venta.asc(), PagoVenta.id_metodo_pago.asc())
            .all()
        )
        for row in pagos_rows:
            try:
                metodo_id = int(row.id_metodo_pago)
            except Exception:
                continue
            esperado_por_metodo[metodo_id] = _money(esperado_por_metodo.get(metodo_id, 0.0)) + _money(row.total)

    venta_ids = sorted(set(venta_ids_auditadas).union(venta_ids_mov_efectivo))
    ventas_rows = []
    if venta_ids:
        ventas_rows = (
            Venta.query.options(joinedload(Venta.cliente))
            .filter(Venta.id_venta.in_(venta_ids))
            .all()
        )
    ventas_por_id = {int(venta.id_venta): venta for venta in ventas_rows}

    efectivo_esperado = 0.0
    if efectivo_id is not None:
        efectivo_esperado = _money(esperado_por_metodo.get(int(efectivo_id), 0.0))
    efectivo_movimientos = sum(row['total'] for row in movimientos_efectivo_rows)
    efectivo_faltante = max(0.0, efectivo_esperado - efectivo_movimientos)
    efectivo_aplicado = efectivo_movimientos + efectivo_faltante

    mostrado_por_metodo = dict(esperado_por_metodo)
    if efectivo_id is not None:
        mostrado_por_metodo[int(efectivo_id)] = efectivo_aplicado

    return {
        'fecha_por_venta': fecha_por_venta,
        'venta_ids_auditadas': sorted(set(venta_ids_auditadas)),
        'venta_ids': venta_ids,
        'ventas_por_id': ventas_por_id,
        'pagos_rows': pagos_rows,
        'esperado_por_metodo': esperado_por_metodo,
        'mostrado_por_metodo': mostrado_por_metodo,
        'movimientos_efectivo_rows': movimientos_efectivo_rows,
        'movimientos_efectivo_por_venta': movimientos_efectivo_por_venta,
        'efectivo_esperado': efectivo_esperado,
        'efectivo_movimientos': efectivo_movimientos,
        'efectivo_faltante': efectivo_faltante,
        'efectivo_aplicado': efectivo_aplicado,
    }
