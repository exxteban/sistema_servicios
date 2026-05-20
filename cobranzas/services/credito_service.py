from datetime import datetime, timedelta
from decimal import Decimal

from app import db
from app.models import CuentaPorCobrar, Venta
from cobranzas import DIAS_VENCIMIENTO_CUENTA_CORRIENTE
from cobranzas.services.cuenta_service import sincronizar_saldos_cuenta
from cobranzas.services.cuotas_service import (
    crear_plan_credito_cuotas,
    estimar_resumen_plan_credito,
    resolver_credito_plan_desde_payload,
)


def resolver_credito_desde_pagos(pagos_normalizados, ids_metodo_credito, total):
    ids_metodo_credito = {int(x) for x in (ids_metodo_credito or set())}
    total = Decimal(str(total or 0))
    precision_tolerancia = Decimal('0.0001')

    if not ids_metodo_credito:
        pagos_inmediatos = list(pagos_normalizados or [])
        total_pagado_inmediato = sum((p['monto'] for p in pagos_inmediatos), Decimal('0'))
        return {
            'es_credito': False,
            'monto_financiado': Decimal('0'),
            'monto_inmediato_exigido': total,
            'total_pagado_inmediato': total_pagado_inmediato,
            'pagos_inmediatos': pagos_inmediatos,
        }, None

    pagos_inmediatos = []
    total_pagado_inmediato = Decimal('0')
    monto_credito_solicitado = Decimal('0')
    for pago in pagos_normalizados or []:
        id_metodo_pago = int(pago['id_metodo_pago'])
        if id_metodo_pago in ids_metodo_credito:
            monto_credito_solicitado += pago['monto']
            continue
        pagos_inmediatos.append(pago)
        total_pagado_inmediato += pago['monto']

    if total_pagado_inmediato - total > precision_tolerancia:
        return None, ({'error': 'El anticipo no puede superar el total de la venta'}, 400)

    monto_financiado = total - total_pagado_inmediato
    if monto_financiado <= precision_tolerancia:
        return None, ({'error': 'La venta no deja saldo para financiar'}, 400)
    if monto_credito_solicitado + precision_tolerancia < monto_financiado:
        return None, ({'error': 'El monto enviado a crédito no cubre el saldo pendiente'}, 400)
    if monto_credito_solicitado - monto_financiado > precision_tolerancia:
        return None, ({'error': 'El monto enviado a crédito supera el saldo pendiente'}, 400)

    return {
        'es_credito': True,
        'monto_financiado': monto_financiado,
        'monto_inmediato_exigido': total_pagado_inmediato,
        'total_pagado_inmediato': total_pagado_inmediato,
        'pagos_inmediatos': pagos_inmediatos,
    }, None


def crear_venta_credito(
    venta: Venta,
    cliente_id: int,
    monto_financiado,
    observaciones: str | None = None,
    *,
    monto_anticipo=0,
    credito_plan: dict | None = None,
) -> CuentaPorCobrar:
    monto_financiado = Decimal(str(monto_financiado or 0))
    if monto_financiado <= 0:
        raise ValueError('El monto financiado debe ser mayor a cero')

    fecha_base = venta.fecha_venta or datetime.utcnow()
    plan_ctx = credito_plan or {'modo': 'cuenta_corriente'}
    if plan_ctx.get('modo') == 'cuotas':
        fecha_vencimiento = plan_ctx['fecha_primer_vencimiento']
    else:
        fecha_vencimiento = (fecha_base + timedelta(days=DIAS_VENCIMIENTO_CUENTA_CORRIENTE)).date()
    cuenta = CuentaPorCobrar(
        id_venta=int(venta.id_venta),
        id_cliente=int(cliente_id),
        monto_total=monto_financiado,
        monto_cobrado=Decimal('0'),
        saldo_pendiente=monto_financiado,
        fecha_vencimiento=fecha_vencimiento,
        estado='pendiente',
        dias_vencido=0,
    )
    if observaciones and hasattr(cuenta, 'observaciones'):
        cuenta.observaciones = observaciones

    venta.tipo_venta = 'credito'
    venta.saldo_pendiente = monto_financiado
    db.session.add(cuenta)
    db.session.flush()
    if plan_ctx.get('modo') == 'cuotas':
        plan_credito = crear_plan_credito_cuotas(
            cuenta,
            monto_financiado=monto_financiado,
            monto_anticipo=monto_anticipo,
            cantidad_cuotas=int(plan_ctx['cantidad_cuotas']),
            frecuencia_dias=int(plan_ctx['frecuencia_dias']),
            fecha_primer_vencimiento=plan_ctx['fecha_primer_vencimiento'],
            tasa_interes_pct=plan_ctx.get('tasa_interes_pct', 0),
            sistema_amortizacion=plan_ctx.get('sistema_amortizacion', 'frances'),
        )
        cuenta.plan_credito_creado = plan_credito
    sincronizar_saldos_cuenta(cuenta)
    return cuenta


def calcular_compromiso_credito(monto_financiado, *, credito_plan: dict | None = None) -> Decimal:
    monto_financiado = Decimal(str(monto_financiado or 0))
    if monto_financiado <= 0:
        return Decimal('0')

    plan_ctx = credito_plan or {}
    if (plan_ctx.get('modo') or '').strip().lower() != 'cuotas':
        return monto_financiado

    resumen_plan = estimar_resumen_plan_credito(
        monto_financiado,
        cantidad_cuotas=int(plan_ctx['cantidad_cuotas']),
        frecuencia_dias=int(plan_ctx['frecuencia_dias']),
        fecha_primer_vencimiento=plan_ctx['fecha_primer_vencimiento'],
        tasa_interes_pct=plan_ctx.get('tasa_interes_pct', 0),
        sistema_amortizacion=plan_ctx.get('sistema_amortizacion', 'frances'),
    )
    return Decimal(str(resumen_plan['monto_total_con_interes'] or 0))


def resolver_credito_plan_payload(payload: dict | None, *, fecha_base=None):
    try:
        return resolver_credito_plan_desde_payload(payload, fecha_base=fecha_base), None
    except ValueError as exc:
        return None, ({'error': str(exc)}, 400)
