from sqlalchemy import func

from app import db
from app.models import Auditoria, Caja, MetodoPago, MovimientoCaja, PagoVenta, SesionCaja, Usuario, Venta
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.utils.helpers import utc_bounds_for_local_dates


def _money(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _rango_utc(args: dict | None):
    rango = resolver_rango(args)
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    return rango, inicio_utc, fin_utc


def caja_resumen_periodo(args: dict | None = None, usuario=None) -> dict:
    rango, inicio_utc, fin_utc = _rango_utc(args)
    movimientos = MovimientoCaja.query.filter(
        MovimientoCaja.fecha_movimiento >= inicio_utc,
        MovimientoCaja.fecha_movimiento < fin_utc,
    )
    ingresos_mov = _money(movimientos.filter(MovimientoCaja.tipo == 'ingreso').with_entities(func.sum(MovimientoCaja.monto)).scalar())
    egresos_mov = _money(movimientos.filter(MovimientoCaja.tipo == 'egreso').with_entities(func.sum(MovimientoCaja.monto)).scalar())
    ventas_total = _money(
        Venta.query.filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        ).with_entities(func.sum(Venta.total)).scalar()
    )
    metodos_rows = (
        db.session.query(
            MetodoPago.nombre,
            func.count(PagoVenta.id_pago).label('cantidad'),
            func.coalesce(func.sum(PagoVenta.monto), 0).label('total'),
        )
        .join(PagoVenta, PagoVenta.id_metodo_pago == MetodoPago.id_metodo_pago)
        .join(Venta, Venta.id_venta == PagoVenta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .group_by(MetodoPago.id_metodo_pago, MetodoPago.nombre)
        .order_by(func.sum(PagoVenta.monto).desc(), MetodoPago.nombre.asc())
        .all()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'desde': rango['desde'].isoformat(),
        'hasta': rango['hasta'].isoformat(),
        'ventas_total': ventas_total,
        'ingresos_movimientos': ingresos_mov,
        'egresos_movimientos': egresos_mov,
        'neto_movimientos': ingresos_mov - egresos_mov,
        'metodos_pago': [
            {'nombre': row.nombre, 'cantidad': int(row.cantidad or 0), 'total': _money(row.total)}
            for row in metodos_rows
        ],
    }


def caja_estado_actual(args: dict | None = None, usuario=None) -> dict:
    top_n = normalizar_top_n((args or {}).get('top_n'), default=5)
    sesiones = (
        SesionCaja.query
        .join(Caja, Caja.id_caja == SesionCaja.id_caja)
        .outerjoin(Usuario, Usuario.id_usuario == SesionCaja.id_usuario)
        .filter(SesionCaja.estado == 'abierta')
        .with_entities(
            SesionCaja.id_sesion,
            Caja.nombre.label('caja'),
            Usuario.username,
            SesionCaja.fecha_apertura,
            SesionCaja.monto_inicial,
        )
        .order_by(SesionCaja.fecha_apertura.asc(), SesionCaja.id_sesion.asc())
        .limit(top_n)
        .all()
    )
    return {
        'cajas_abiertas': len(sesiones),
        'sesiones': [
            {
                'id_sesion': row.id_sesion,
                'caja': row.caja,
                'usuario': row.username,
                'fecha_apertura': row.fecha_apertura.isoformat() if row.fecha_apertura else None,
                'monto_inicial': _money(row.monto_inicial),
            }
            for row in sesiones
        ],
    }


def caja_anulaciones_periodo(args: dict | None = None, usuario=None) -> dict:
    rango, inicio_utc, fin_utc = _rango_utc(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    filtros = (
        Auditoria.accion == 'anular_venta',
        Auditoria.modulo == 'ventas',
        Auditoria.referencia_tipo == 'venta',
        Auditoria.fecha_accion >= inicio_utc,
        Auditoria.fecha_accion < fin_utc,
    )
    cantidad_total = Auditoria.query.filter(*filtros).count()
    monto_ventas_anuladas = _money(
        db.session.query(func.coalesce(func.sum(Venta.total), 0))
        .join(Auditoria, Auditoria.referencia_id == Venta.id_venta)
        .filter(*filtros)
        .scalar()
    )
    auditorias = (
        Auditoria.query
        .filter(*filtros)
        .order_by(Auditoria.fecha_accion.desc(), Auditoria.id_auditoria.desc())
        .limit(top_n)
        .all()
    )
    venta_ids = []
    for audit in auditorias:
        try:
            venta_ids.append(int(audit.referencia_id))
        except Exception:
            continue
    ventas = {
        int(venta.id_venta): venta
        for venta in Venta.query.filter(Venta.id_venta.in_(venta_ids)).all()
    } if venta_ids else {}
    movimientos_total = _money(
        MovimientoCaja.query.filter(
            MovimientoCaja.tipo == 'egreso',
            MovimientoCaja.referencia_tipo == 'anulacion_venta',
            MovimientoCaja.fecha_movimiento >= inicio_utc,
            MovimientoCaja.fecha_movimiento < fin_utc,
        ).with_entities(func.sum(MovimientoCaja.monto)).scalar()
    )
    items = []
    for audit in auditorias:
        venta = ventas.get(int(audit.referencia_id or 0))
        items.append({
            'id_auditoria': audit.id_auditoria,
            'id_venta': int(audit.referencia_id or 0),
            'fecha': audit.fecha_accion.isoformat() if audit.fecha_accion else None,
            'monto_venta': _money(getattr(venta, 'total', 0)),
            'descripcion': (audit.descripcion or '')[:180],
        })
    return {
        'periodo_label': rango['periodo_label'],
        'cantidad_anulaciones': int(cantidad_total or 0),
        'monto_ventas_anuladas': monto_ventas_anuladas,
        'monto_egresos_anulacion': movimientos_total,
        'anulaciones': items,
    }
