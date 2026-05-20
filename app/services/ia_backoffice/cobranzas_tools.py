from datetime import timedelta

from sqlalchemy import func

from app import db
from app.models import Cliente, CuentaPorCobrar, PagoCuentaCobrar
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.utils.helpers import today_local, utc_bounds_for_local_dates


def cobranzas_resumen(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    hoy = today_local()
    base = CuentaPorCobrar.query.filter(CuentaPorCobrar.estado != 'anulada')
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    cobrado_periodo = (
        db.session.query(func.coalesce(func.sum(PagoCuentaCobrar.monto), 0))
        .filter(
            PagoCuentaCobrar.estado != 'anulado',
            PagoCuentaCobrar.fecha_pago >= inicio_utc,
            PagoCuentaCobrar.fecha_pago < fin_utc,
        )
        .scalar()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'saldo_total': float(base.with_entities(func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente), 0)).scalar() or 0),
        'cuentas_abiertas': int(base.filter(CuentaPorCobrar.saldo_pendiente > 0).count()),
        'cuentas_vencidas': int(base.filter(
            CuentaPorCobrar.saldo_pendiente > 0,
            CuentaPorCobrar.fecha_vencimiento.isnot(None),
            CuentaPorCobrar.fecha_vencimiento < hoy,
        ).count()),
        'cobrado_periodo': float(cobrado_periodo or 0),
    }


def cobranzas_clientes_morosos(args: dict | None = None, usuario=None) -> dict:
    top_n = normalizar_top_n((args or {}).get('top_n'))
    hoy = today_local()
    filas = (
        db.session.query(
            Cliente.id_cliente,
            Cliente.nombre,
            func.count(CuentaPorCobrar.id_cuenta_cobrar).label('cuentas_vencidas'),
            func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente), 0).label('saldo_vencido'),
            func.max(CuentaPorCobrar.dias_vencido).label('dias_vencido_max'),
        )
        .join(CuentaPorCobrar, CuentaPorCobrar.id_cliente == Cliente.id_cliente)
        .filter(
            CuentaPorCobrar.estado != 'anulada',
            CuentaPorCobrar.saldo_pendiente > 0,
            CuentaPorCobrar.fecha_vencimiento.isnot(None),
            CuentaPorCobrar.fecha_vencimiento < hoy,
        )
        .group_by(Cliente.id_cliente, Cliente.nombre)
        .order_by(func.sum(CuentaPorCobrar.saldo_pendiente).desc(), Cliente.nombre.asc())
        .limit(top_n)
        .all()
    )
    return {
        'fecha_referencia': hoy.isoformat(),
        'top_n': top_n,
        'clientes': [
            {
                'id_cliente': row.id_cliente,
                'nombre': row.nombre,
                'cuentas_vencidas': int(row.cuentas_vencidas or 0),
                'saldo_vencido': float(row.saldo_vencido or 0),
                'dias_vencido_max': int(row.dias_vencido_max or 0),
            }
            for row in filas
        ],
    }


def cobranzas_proximos_vencimientos(args: dict | None = None, usuario=None) -> dict:
    top_n = normalizar_top_n((args or {}).get('top_n'))
    hoy = today_local()
    hasta = hoy + timedelta(days=7)
    filas = (
        CuentaPorCobrar.query
        .join(Cliente, Cliente.id_cliente == CuentaPorCobrar.id_cliente)
        .filter(
            CuentaPorCobrar.estado != 'anulada',
            CuentaPorCobrar.saldo_pendiente > 0,
            CuentaPorCobrar.fecha_vencimiento.isnot(None),
            CuentaPorCobrar.fecha_vencimiento >= hoy,
            CuentaPorCobrar.fecha_vencimiento <= hasta,
        )
        .with_entities(
            CuentaPorCobrar.id_cuenta_cobrar,
            CuentaPorCobrar.id_cliente,
            Cliente.nombre.label('cliente'),
            CuentaPorCobrar.fecha_vencimiento,
            CuentaPorCobrar.saldo_pendiente,
        )
        .order_by(CuentaPorCobrar.fecha_vencimiento.asc(), CuentaPorCobrar.saldo_pendiente.desc())
        .limit(top_n)
        .all()
    )
    return {
        'desde': hoy.isoformat(),
        'hasta': hasta.isoformat(),
        'vencimientos': [
            {
                'id_cuenta_cobrar': row.id_cuenta_cobrar,
                'id_cliente': row.id_cliente,
                'cliente': row.cliente,
                'fecha_vencimiento': row.fecha_vencimiento.isoformat() if row.fecha_vencimiento else None,
                'saldo_pendiente': float(row.saldo_pendiente or 0),
            }
            for row in filas
        ],
    }
