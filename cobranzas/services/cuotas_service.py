from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_DOWN

from sqlalchemy import func

from app import db
from cobranzas.models import CuotaCreditoVenta, PagoCuentaCobrarAplicacion, PlanCreditoVenta


_MONEY_QUANTIZER = Decimal('0.01')
_TOLERANCIA = Decimal('0.0001')
_RATE_QUANTIZER = Decimal('0.0001')


def _decimal_positivo(value) -> Decimal:
    try:
        numero = Decimal(str(value or 0))
    except Exception:
        numero = Decimal('0')
    if numero < 0:
        return Decimal('0')
    return numero


def _money(value) -> Decimal:
    return _decimal_positivo(value).quantize(_MONEY_QUANTIZER)


def _rate(value) -> Decimal:
    return _decimal_positivo(value).quantize(_RATE_QUANTIZER)


def _cuotas_ordenadas(plan: PlanCreditoVenta) -> list[CuotaCreditoVenta]:
    return sorted(
        list(getattr(plan, 'cuotas', []) or []),
        key=lambda cuota: (int(getattr(cuota, 'numero_cuota', 0) or 0), int(getattr(cuota, 'id_cuota_credito', 0) or 0)),
    )


def _componentes_programados_cuota(cuota: CuotaCreditoVenta) -> tuple[Decimal, Decimal, Decimal]:
    monto_programado = _money(getattr(cuota, 'monto_programado', 0))
    interes_programado = _money(getattr(cuota, 'interes_programado', 0))
    capital_programado = _money(getattr(cuota, 'capital_programado', 0))

    if interes_programado > monto_programado:
        interes_programado = monto_programado

    if (
        monto_programado > _TOLERANCIA
        and capital_programado <= _TOLERANCIA
        and interes_programado <= _TOLERANCIA
    ):
        capital_programado = monto_programado
    else:
        total_componentes = capital_programado + interes_programado
        if capital_programado <= _TOLERANCIA or abs(total_componentes - monto_programado) > _TOLERANCIA:
            capital_programado = _money(monto_programado - interes_programado)

    return monto_programado, capital_programado, interes_programado


def _capital_cobrado_en_cuota(cuota: CuotaCreditoVenta) -> Decimal:
    monto_cobrado = _money(getattr(cuota, 'monto_cobrado', 0))
    _, capital_programado, interes_programado = _componentes_programados_cuota(cuota)

    interes_cubierto = min(monto_cobrado, interes_programado)
    capital_cobrado = _money(monto_cobrado - interes_cubierto)
    if capital_cobrado > capital_programado:
        capital_cobrado = capital_programado
    return capital_cobrado


def _principal_plan(plan: PlanCreditoVenta, cuotas_ordenadas: list[CuotaCreditoVenta]) -> Decimal:
    principal = _money(getattr(plan, 'monto_total_financiado', 0))
    if principal > _TOLERANCIA:
        return principal
    return _money(sum((_componentes_programados_cuota(cuota)[1] for cuota in cuotas_ordenadas), Decimal('0')))


def _date_or_default(value, *, default: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    texto = str(value or '').strip()
    if not texto:
        return default
    try:
        return date.fromisoformat(texto)
    except Exception as exc:
        raise ValueError('La fecha del primer vencimiento es invalida') from exc


def obtener_plan_credito_vigente(cuenta, *, for_update: bool = False) -> PlanCreditoVenta | None:
    if cuenta is None or getattr(cuenta, 'id_cuenta_cobrar', None) is None:
        return None
    query = (
        PlanCreditoVenta.query
        .filter(
            PlanCreditoVenta.id_cuenta_cobrar == int(cuenta.id_cuenta_cobrar),
            PlanCreditoVenta.estado.notin_(('anulado', 'refinanciado')),
        )
        .order_by(PlanCreditoVenta.id_plan_credito_venta.desc())
    )
    if for_update:
        query = query.populate_existing().with_for_update()
    plan = query.first()
    if plan is None:
        return None
    if for_update:
        (
            CuotaCreditoVenta.query
            .filter(CuotaCreditoVenta.id_plan_credito_venta == int(plan.id_plan_credito_venta))
            .order_by(CuotaCreditoVenta.numero_cuota.asc(), CuotaCreditoVenta.id_cuota_credito.asc())
            .populate_existing()
            .with_for_update()
            .all()
        )
    return plan


def resolver_credito_plan_desde_payload(payload: dict | None, *, fecha_base: date | None = None) -> dict:
    fecha_base = fecha_base or date.today()
    payload = payload or {}
    modo = str(payload.get('credito_modo') or 'cuenta_corriente').strip().lower() or 'cuenta_corriente'
    if modo != 'cuotas':
        return {'modo': 'cuenta_corriente'}

    plan_payload = payload.get('credito_plan') or {}
    try:
        cantidad_cuotas = int(plan_payload.get('cantidad_cuotas') or plan_payload.get('cuotas') or 0)
    except Exception as exc:
        raise ValueError('La cantidad de cuotas es invalida') from exc
    if cantidad_cuotas < 2:
        raise ValueError('Las ventas en cuotas requieren al menos 2 cuotas')
    if cantidad_cuotas > 60:
        raise ValueError('La cantidad de cuotas no puede superar 60')

    try:
        frecuencia_dias = int(plan_payload.get('frecuencia_dias') or 30)
    except Exception as exc:
        raise ValueError('La frecuencia de cuotas es invalida') from exc
    if frecuencia_dias <= 0 or frecuencia_dias > 365:
        raise ValueError('La frecuencia de cuotas debe estar entre 1 y 365 dias')

    fecha_primer_vencimiento = _date_or_default(
        plan_payload.get('fecha_primer_vencimiento'),
        default=fecha_base + timedelta(days=frecuencia_dias),
    )
    if fecha_primer_vencimiento < fecha_base:
        raise ValueError('La fecha del primer vencimiento no puede ser anterior a la venta')

    tasa_interes_pct = _rate(
        plan_payload.get('tasa_interes_pct')
        if plan_payload.get('tasa_interes_pct') is not None
        else plan_payload.get('tasa_periodica_pct')
    )
    if tasa_interes_pct > Decimal('100'):
        raise ValueError('La tasa de interes por cuota no puede superar 100%')

    sistema_amortizacion = str(plan_payload.get('sistema_amortizacion') or 'frances').strip().lower() or 'frances'
    if sistema_amortizacion != 'frances':
        raise ValueError('El sistema de amortizacion no es valido')

    return {
        'modo': 'cuotas',
        'cantidad_cuotas': cantidad_cuotas,
        'frecuencia_dias': frecuencia_dias,
        'fecha_primer_vencimiento': fecha_primer_vencimiento,
        'tasa_interes_pct': tasa_interes_pct,
        'sistema_amortizacion': sistema_amortizacion,
    }


def generar_calendario_cuotas(
    monto_total,
    *,
    cantidad_cuotas: int,
    fecha_primer_vencimiento: date,
    frecuencia_dias: int,
    tasa_interes_pct=0,
    sistema_amortizacion: str = 'frances',
) -> list[dict]:
    monto_principal = _money(monto_total)
    if monto_principal <= 0:
        raise ValueError('El monto financiado debe ser mayor a cero')
    if cantidad_cuotas <= 0:
        raise ValueError('La cantidad de cuotas es invalida')
    if (sistema_amortizacion or '').strip().lower() != 'frances':
        raise ValueError('El sistema de amortizacion no es valido')

    tasa_periodica_pct = _rate(tasa_interes_pct)
    tasa_periodica = tasa_periodica_pct / Decimal('100')

    # Con tasa cero mantenemos distribucion lineal de capital.
    if tasa_periodica <= _TOLERANCIA:
        monto_base = (monto_principal / Decimal(cantidad_cuotas)).quantize(_MONEY_QUANTIZER, rounding=ROUND_DOWN)
        saldo_por_distribuir = monto_principal - (monto_base * cantidad_cuotas)
        saldo_capital = monto_principal
        calendario = []
        for indice in range(cantidad_cuotas):
            capital_cuota = monto_base
            if indice == cantidad_cuotas - 1:
                capital_cuota += saldo_por_distribuir
            capital_cuota = _money(capital_cuota)
            saldo_capital = _money(saldo_capital - capital_cuota)
            calendario.append(
                {
                    'numero_cuota': indice + 1,
                    'fecha_vencimiento': fecha_primer_vencimiento + timedelta(days=frecuencia_dias * indice),
                    'capital_programado': capital_cuota,
                    'interes_programado': Decimal('0.00'),
                    'monto_programado': capital_cuota,
                    'saldo_capital': saldo_capital,
                }
            )
        return calendario

    # Sistema frances: cuota fija teorica, con ajuste monetario controlado en la ultima cuota.
    potencia = (Decimal('1') + tasa_periodica) ** int(cantidad_cuotas)
    cuota_teorica = monto_principal * ((tasa_periodica * potencia) / (potencia - Decimal('1')))
    cuota_programada = _money(cuota_teorica)

    saldo_capital = monto_principal
    calendario = []
    for indice in range(cantidad_cuotas):
        interes_cuota = _money(saldo_capital * tasa_periodica)
        if indice == cantidad_cuotas - 1:
            capital_cuota = _money(saldo_capital)
            monto_cuota = _money(capital_cuota + interes_cuota)
        else:
            capital_cuota = _money(cuota_programada - interes_cuota)
            if capital_cuota > saldo_capital:
                capital_cuota = _money(saldo_capital)
            monto_cuota = _money(capital_cuota + interes_cuota)
        saldo_capital = _money(saldo_capital - capital_cuota)
        calendario.append(
            {
                'numero_cuota': indice + 1,
                'fecha_vencimiento': fecha_primer_vencimiento + timedelta(days=frecuencia_dias * indice),
                'capital_programado': capital_cuota,
                'interes_programado': interes_cuota,
                'monto_programado': monto_cuota,
                'saldo_capital': saldo_capital,
            }
    )
    return calendario


def estimar_resumen_plan_credito(
    monto_financiado,
    *,
    cantidad_cuotas: int,
    fecha_primer_vencimiento: date,
    frecuencia_dias: int,
    tasa_interes_pct=0,
    sistema_amortizacion: str = 'frances',
) -> dict:
    calendario_cuotas = generar_calendario_cuotas(
        monto_financiado,
        cantidad_cuotas=int(cantidad_cuotas),
        fecha_primer_vencimiento=fecha_primer_vencimiento,
        frecuencia_dias=int(frecuencia_dias),
        tasa_interes_pct=tasa_interes_pct,
        sistema_amortizacion=sistema_amortizacion,
    )
    monto_total_interes = _money(sum((cuota['interes_programado'] for cuota in calendario_cuotas), Decimal('0')))
    monto_total_con_interes = _money(sum((cuota['monto_programado'] for cuota in calendario_cuotas), Decimal('0')))
    return {
        'calendario_cuotas': calendario_cuotas,
        'monto_total_interes': monto_total_interes,
        'monto_total_con_interes': monto_total_con_interes,
    }


def crear_plan_credito_cuotas(
    cuenta,
    *,
    monto_financiado,
    monto_anticipo=0,
    cantidad_cuotas: int,
    frecuencia_dias: int,
    fecha_primer_vencimiento: date,
    tasa_interes_pct=0,
    sistema_amortizacion: str = 'frances',
) -> PlanCreditoVenta:
    monto_financiado = _money(monto_financiado)
    monto_anticipo = _money(monto_anticipo)
    tasa_interes_pct = _rate(tasa_interes_pct)
    sistema_amortizacion = (sistema_amortizacion or 'frances').strip().lower() or 'frances'

    resumen_plan = estimar_resumen_plan_credito(
        monto_financiado,
        cantidad_cuotas=int(cantidad_cuotas),
        fecha_primer_vencimiento=fecha_primer_vencimiento,
        frecuencia_dias=int(frecuencia_dias),
        tasa_interes_pct=tasa_interes_pct,
        sistema_amortizacion=sistema_amortizacion,
    )
    calendario_cuotas = resumen_plan['calendario_cuotas']
    monto_total_interes = resumen_plan['monto_total_interes']
    monto_total_con_interes = resumen_plan['monto_total_con_interes']

    plan = PlanCreditoVenta(
        id_cuenta_cobrar=int(cuenta.id_cuenta_cobrar),
        modo='cuotas',
        cantidad_cuotas=int(cantidad_cuotas),
        frecuencia_dias=int(frecuencia_dias),
        fecha_primer_vencimiento=fecha_primer_vencimiento,
        monto_total_financiado=monto_financiado,
        tasa_periodica_pct=tasa_interes_pct,
        sistema_amortizacion=sistema_amortizacion,
        monto_total_interes=monto_total_interes,
        monto_total_con_interes=monto_total_con_interes,
        monto_anticipo=monto_anticipo,
        monto_cobrado=Decimal('0'),
        saldo_pendiente=monto_total_con_interes,
        estado='pendiente',
    )
    db.session.add(plan)
    db.session.flush()

    for cuota_data in calendario_cuotas:
        cuota = CuotaCreditoVenta(
            id_plan_credito_venta=int(plan.id_plan_credito_venta),
            numero_cuota=int(cuota_data['numero_cuota']),
            fecha_vencimiento=cuota_data['fecha_vencimiento'],
            capital_programado=cuota_data['capital_programado'],
            interes_programado=cuota_data['interes_programado'],
            saldo_capital=cuota_data['saldo_capital'],
            monto_programado=cuota_data['monto_programado'],
            monto_cobrado=Decimal('0'),
            saldo_pendiente=cuota_data['monto_programado'],
            estado='pendiente',
            dias_vencido=0,
        )
        db.session.add(cuota)

    db.session.flush()
    return plan


def _resolver_estado_cuota(cuota: CuotaCreditoVenta, *, fecha: date | None = None) -> tuple[Decimal, str, int]:
    fecha_ref = fecha or date.today()
    saldo = _money(cuota.monto_programado) - _money(cuota.monto_cobrado)
    if saldo <= _TOLERANCIA:
        return Decimal('0.00'), 'pagada', 0
    if cuota.fecha_vencimiento and cuota.fecha_vencimiento < fecha_ref:
        return _money(saldo), 'vencida', (fecha_ref - cuota.fecha_vencimiento).days
    return _money(saldo), 'pendiente', 0


def sincronizar_plan_credito(plan: PlanCreditoVenta, *, fecha: date | None = None) -> PlanCreditoVenta:
    fecha_ref = fecha or date.today()
    cuotas_ordenadas = _cuotas_ordenadas(plan)
    cuotas_ids = [int(cuota.id_cuota_credito) for cuota in cuotas_ordenadas]
    pagos_por_cuota = {}
    if cuotas_ids:
        filas = (
            db.session.query(
                PagoCuentaCobrarAplicacion.id_cuota_credito,
                func.coalesce(func.sum(PagoCuentaCobrarAplicacion.monto_aplicado), 0),
                func.max(PagoCuentaCobrarAplicacion.created_at),
            )
            .join(PagoCuentaCobrarAplicacion.pago)
            .filter(
                PagoCuentaCobrarAplicacion.id_cuota_credito.in_(cuotas_ids),
                PagoCuentaCobrarAplicacion.pago.has(estado='activo'),
            )
            .group_by(PagoCuentaCobrarAplicacion.id_cuota_credito)
            .all()
        )
        pagos_por_cuota = {
            int(id_cuota): (_money(total), fecha_ultimo_pago)
            for id_cuota, total, fecha_ultimo_pago in filas
        }

    monto_cobrado_total = Decimal('0.00')
    saldo_total = Decimal('0.00')
    cuotas_vencidas = 0
    cuotas_pendientes = 0
    saldo_capital_restante = _principal_plan(plan, cuotas_ordenadas)
    for cuota in cuotas_ordenadas:
        monto_cobrado, fecha_ultimo_pago = pagos_por_cuota.get(int(cuota.id_cuota_credito), (Decimal('0.00'), None))
        cuota.monto_cobrado = monto_cobrado
        cuota.fecha_ultimo_pago = fecha_ultimo_pago
        saldo_cuota, estado_cuota, dias_vencido = _resolver_estado_cuota(cuota, fecha=fecha_ref)
        cuota.saldo_pendiente = saldo_cuota
        cuota.estado = estado_cuota
        cuota.dias_vencido = dias_vencido
        capital_cobrado = _capital_cobrado_en_cuota(cuota)
        saldo_capital_restante = _money(saldo_capital_restante - capital_cobrado)
        cuota.saldo_capital = saldo_capital_restante
        monto_cobrado_total += _money(monto_cobrado)
        saldo_total += _money(saldo_cuota)
        if estado_cuota == 'vencida':
            cuotas_vencidas += 1
        elif estado_cuota == 'pendiente':
            cuotas_pendientes += 1

    plan.monto_cobrado = _money(monto_cobrado_total)
    plan.saldo_pendiente = _money(saldo_total)
    if plan.saldo_pendiente <= _TOLERANCIA:
        plan.estado = 'pagado'
    elif cuotas_vencidas > 0:
        plan.estado = 'vencido'
    elif cuotas_pendientes > 0:
        plan.estado = 'pendiente'
    else:
        plan.estado = 'pendiente'
    return plan


def imputar_pago_a_cuotas(cuenta, pago) -> list[PagoCuentaCobrarAplicacion]:
    plan = obtener_plan_credito_vigente(cuenta)
    if plan is None or (plan.modo or '').strip().lower() != 'cuotas':
        return []

    sincronizar_plan_credito(plan, fecha=(pago.fecha_pago.date() if getattr(pago, 'fecha_pago', None) else None))

    restante = _money(getattr(pago, 'monto', 0))
    aplicaciones = []
    cuotas_abiertas = [
        cuota for cuota in plan.cuotas
        if _money(cuota.saldo_pendiente) > _TOLERANCIA and (cuota.estado or '').strip().lower() not in ('cancelada', 'refinanciada')
    ]
    cuotas_abiertas.sort(key=lambda cuota: (cuota.fecha_vencimiento or date.max, cuota.numero_cuota, cuota.id_cuota_credito))

    for cuota in cuotas_abiertas:
        if restante <= _TOLERANCIA:
            break
        saldo_cuota = _money(cuota.saldo_pendiente)
        if saldo_cuota <= _TOLERANCIA:
            continue
        monto_aplicado = min(restante, saldo_cuota)
        aplicacion = PagoCuentaCobrarAplicacion(
            id_pago_cuenta=int(pago.id_pago_cuenta),
            id_cuota_credito=int(cuota.id_cuota_credito),
            monto_aplicado=_money(monto_aplicado),
        )
        db.session.add(aplicacion)
        aplicaciones.append(aplicacion)
        restante -= _money(monto_aplicado)

    if restante > _TOLERANCIA:
        raise ValueError('No se pudo imputar el pago completo a las cuotas vigentes')

    db.session.flush()
    sincronizar_plan_credito(plan, fecha=(pago.fecha_pago.date() if getattr(pago, 'fecha_pago', None) else None))
    return aplicaciones
