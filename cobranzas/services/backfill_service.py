from decimal import Decimal

from sqlalchemy import func, or_

from app import db
from app.models import CuentaPorCobrar, Venta
from cobranzas.services.credito_service import crear_venta_credito


def _decimal_positivo(value) -> Decimal:
    try:
        numero = Decimal(str(value or 0))
    except Exception:
        numero = Decimal('0')
    if numero < 0:
        return Decimal('0')
    return numero


def backfill_cuentas_por_cobrar_ventas_credito(*, dry_run: bool = True, limit: int | None = None) -> dict:
    query = (
        Venta.query.outerjoin(CuentaPorCobrar, CuentaPorCobrar.id_venta == Venta.id_venta)
        .filter(CuentaPorCobrar.id_cuenta_cobrar.is_(None))
        .filter(Venta.estado != 'anulada')
        .filter(
            or_(
                Venta.saldo_pendiente > 0,
                func.lower(func.coalesce(Venta.tipo_venta, '')) == 'credito',
            )
        )
        .order_by(Venta.id_venta.asc())
    )
    if limit:
        query = query.limit(max(int(limit), 1))

    candidatas = []
    omitidas = []
    for venta in query.all():
        saldo_pendiente = _decimal_positivo(venta.saldo_pendiente)
        if not getattr(venta, 'id_cliente', None):
            omitidas.append({'id_venta': int(venta.id_venta), 'motivo': 'sin_cliente'})
            continue
        if saldo_pendiente <= 0:
            omitidas.append({'id_venta': int(venta.id_venta), 'motivo': 'sin_saldo'})
            continue
        candidatas.append(
            {
                'venta': venta,
                'id_venta': int(venta.id_venta),
                'id_cliente': int(venta.id_cliente),
                'saldo_pendiente': float(saldo_pendiente),
            }
        )

    resultado = {
        'dry_run': bool(dry_run),
        'detectadas': len(candidatas),
        'creadas': 0,
        'omitidas': omitidas,
        'ventas': [
            {
                'id_venta': item['id_venta'],
                'id_cliente': item['id_cliente'],
                'saldo_pendiente': item['saldo_pendiente'],
            }
            for item in candidatas
        ],
    }

    if dry_run or not candidatas:
        return resultado

    try:
        for item in candidatas:
            crear_venta_credito(
                item['venta'],
                item['id_cliente'],
                item['saldo_pendiente'],
                observaciones='Cuenta creada por backfill idempotente de ventas credito.',
            )
            resultado['creadas'] += 1
        db.session.commit()
        return resultado
    except Exception:
        db.session.rollback()
        raise
