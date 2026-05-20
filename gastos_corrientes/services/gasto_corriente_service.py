from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation

from flask_login import current_user

from app import db
from app.models import MovimientoCaja, SesionCaja
from app.utils.helpers import utc_bounds_for_local_dates
from gastos_corrientes.models import GastoCorriente, PagoGastoCorriente


def _usuario_actual():
    try:
        getter = getattr(current_user, '_get_current_object', None)
        return getter() if callable(getter) else current_user
    except Exception:
        return None


def cliente_scope_actual() -> int | None:
    usuario = _usuario_actual()
    try:
        cliente_id = int(getattr(usuario, 'id_cliente', 0) or 0)
    except (TypeError, ValueError):
        cliente_id = 0
    return cliente_id or None


def aplicar_scope_cliente(query, model):
    cliente_scope = cliente_scope_actual()
    if cliente_scope:
        return query.filter(getattr(model, 'cliente_id') == cliente_scope)
    usuario = _usuario_actual()
    if usuario is None:
        return query.filter(getattr(model, 'cliente_id').is_(None))
    return query if usuario.es_admin() else query.filter(getattr(model, 'cliente_id').is_(None))


def obtener_gasto_o_404(id_gasto_corriente: int) -> GastoCorriente:
    return aplicar_scope_cliente(GastoCorriente.query, GastoCorriente).filter(
        GastoCorriente.id_gasto_corriente == id_gasto_corriente,
    ).first_or_404()


def obtener_pago_o_404(id_pago_gasto_corriente: int) -> PagoGastoCorriente:
    return aplicar_scope_cliente(PagoGastoCorriente.query, PagoGastoCorriente).filter(
        PagoGastoCorriente.id_pago_gasto_corriente == id_pago_gasto_corriente,
    ).first_or_404()


def parse_decimal(raw_value: str | None) -> Decimal | None:
    texto = (raw_value or '').strip().replace(' ', '')
    if not texto:
        return None
    if ',' in texto and '.' in texto:
        if texto.rfind(',') > texto.rfind('.'):
            texto = texto.replace('.', '').replace(',', '.')
        else:
            texto = texto.replace(',', '')
    elif ',' in texto:
        texto = texto.replace(',', '.')
    try:
        return Decimal(texto).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def parse_fecha(raw_value: str | None) -> date | None:
    texto = (raw_value or '').strip()
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _fecha_pago_movimiento(fecha_pago: date):
    start_utc, _ = utc_bounds_for_local_dates(fecha_pago, fecha_pago)
    return start_utc


def parse_periodo(raw_value: str | None, today: date | None = None) -> tuple[int, int, str]:
    referencia = today or date.today()
    texto = (raw_value or '').strip()
    if len(texto) == 7 and texto[4] == '-':
        try:
            anio = int(texto[:4])
            mes = int(texto[5:])
            if 1 <= mes <= 12:
                return anio, mes, f'{anio:04d}-{mes:02d}'
        except ValueError:
            pass
    return referencia.year, referencia.month, f'{referencia.year:04d}-{referencia.month:02d}'


def resolver_fecha_vencimiento(gasto: GastoCorriente, periodo_anio: int, periodo_mes: int) -> date:
    dia = max(1, min(int(gasto.dia_vencimiento_int() or 1), monthrange(periodo_anio, periodo_mes)[1]))
    return date(periodo_anio, periodo_mes, dia)


def gasto_aplica_en_periodo(gasto: GastoCorriente, periodo_anio: int, periodo_mes: int) -> bool:
    fecha_creacion = getattr(gasto, 'fecha_creacion', None)
    if fecha_creacion is None:
        return True

    fecha_creacion = fecha_creacion.date() if hasattr(fecha_creacion, 'date') else fecha_creacion
    if fecha_creacion.year != periodo_anio or fecha_creacion.month != periodo_mes:
        return True

    return fecha_creacion <= resolver_fecha_vencimiento(gasto, periodo_anio, periodo_mes)


def sincronizar_pagos_periodo(
    *,
    periodo_anio: int,
    periodo_mes: int,
    commit: bool = True,
) -> dict:
    gastos = (
        aplicar_scope_cliente(GastoCorriente.query, GastoCorriente)
        .filter(GastoCorriente.activo.is_(True))
        .order_by(GastoCorriente.id_gasto_corriente.asc())
        .all()
    )
    if not gastos:
        return {'created': 0, 'updated': 0, 'existing': 0}

    gasto_ids = [int(gasto.id_gasto_corriente) for gasto in gastos]
    pagos = (
        aplicar_scope_cliente(PagoGastoCorriente.query, PagoGastoCorriente)
        .filter(
            PagoGastoCorriente.id_gasto_corriente.in_(gasto_ids),
            PagoGastoCorriente.periodo_anio == periodo_anio,
            PagoGastoCorriente.periodo_mes == periodo_mes,
        )
        .order_by(PagoGastoCorriente.id_pago_gasto_corriente.asc())
        .all()
    )
    pagos_por_gasto: dict[int, list[PagoGastoCorriente]] = {}
    for pago in pagos:
        pagos_por_gasto.setdefault(int(pago.id_gasto_corriente), []).append(pago)

    created = 0
    updated = 0
    existing = 0
    cliente_id = cliente_scope_actual()

    for gasto in gastos:
        if not gasto_aplica_en_periodo(gasto, periodo_anio, periodo_mes):
            continue

        gasto_id = int(gasto.id_gasto_corriente)
        fecha_vencimiento = resolver_fecha_vencimiento(gasto, periodo_anio, periodo_mes)
        pagos_gasto = pagos_por_gasto.get(gasto_id, [])
        activos = [pago for pago in pagos_gasto if not pago.esta_anulado()]

        if activos:
            pago_activo = activos[-1]
            if (pago_activo.estado or '').strip().lower() == 'pendiente':
                dirty = False
                monto_estimado = gasto.monto_estimado_decimal()
                if pago_activo.monto_estimado_decimal() != monto_estimado:
                    pago_activo.monto_estimado = monto_estimado
                    dirty = True
                if pago_activo.fecha_vencimiento != fecha_vencimiento:
                    pago_activo.fecha_vencimiento = fecha_vencimiento
                    dirty = True
                if pago_activo.cliente_id != cliente_id:
                    pago_activo.cliente_id = cliente_id
                    dirty = True
                if dirty:
                    updated += 1
                else:
                    existing += 1
            else:
                existing += 1
            continue

        db.session.add(
            PagoGastoCorriente(
                cliente_id=cliente_id,
                id_gasto_corriente=gasto_id,
                periodo_anio=periodo_anio,
                periodo_mes=periodo_mes,
                fecha_vencimiento=fecha_vencimiento,
                fecha_pago=None,
                monto_estimado=gasto.monto_estimado_decimal(),
                monto_pagado=Decimal('0.00'),
                estado='pendiente',
                pagado_desde_caja=False,
                observacion='Generado automáticamente para seguimiento mensual.',
            )
        )
        created += 1

    if created or updated:
        db.session.flush()
        if commit:
            db.session.commit()
    return {'created': created, 'updated': updated, 'existing': existing}


def _obtener_sesion_abierta_para_pago() -> SesionCaja | None:
    return SesionCaja.query.filter_by(
        id_usuario=current_user.id_usuario,
        estado='abierta',
    ).first()


def registrar_pago_gasto(
    gasto: GastoCorriente,
    *,
    periodo_anio: int,
    periodo_mes: int,
    fecha_pago: date,
    monto_pagado: Decimal,
    observacion: str | None,
    numero_comprobante: str | None,
    pagado_desde_caja: bool,
) -> tuple[PagoGastoCorriente, MovimientoCaja | None]:
    existente = aplicar_scope_cliente(PagoGastoCorriente.query, PagoGastoCorriente).filter(
        PagoGastoCorriente.id_gasto_corriente == gasto.id_gasto_corriente,
        PagoGastoCorriente.periodo_anio == periodo_anio,
        PagoGastoCorriente.periodo_mes == periodo_mes,
        PagoGastoCorriente.estado != 'anulado',
    ).order_by(PagoGastoCorriente.id_pago_gasto_corriente.desc()).first()

    pago = None
    if existente:
        estado_existente = (existente.estado or '').strip().lower()
        if estado_existente == 'pendiente':
            pago = existente
        else:
            raise ValueError('Ya existe un pago activo para este gasto y período.')

    sesion_caja = None
    if pagado_desde_caja:
        sesion_caja = _obtener_sesion_abierta_para_pago()
        if not sesion_caja:
            raise ValueError('Debe tener una caja abierta para registrar un pago desde caja.')

    if pago is None:
        pago = PagoGastoCorriente(
            cliente_id=cliente_scope_actual(),
            id_gasto_corriente=gasto.id_gasto_corriente,
            periodo_anio=periodo_anio,
            periodo_mes=periodo_mes,
            fecha_vencimiento=resolver_fecha_vencimiento(gasto, periodo_anio, periodo_mes),
            fecha_pago=fecha_pago,
            monto_estimado=gasto.monto_estimado_decimal(),
            monto_pagado=monto_pagado,
            estado='pagado',
            pagado_desde_caja=bool(pagado_desde_caja),
            id_sesion_caja=sesion_caja.id_sesion if sesion_caja else None,
            id_usuario=current_user.id_usuario,
            observacion=observacion or None,
            numero_comprobante=numero_comprobante or None,
        )
        db.session.add(pago)
        db.session.flush()
    else:
        pago.cliente_id = cliente_scope_actual()
        pago.fecha_vencimiento = resolver_fecha_vencimiento(gasto, periodo_anio, periodo_mes)
        pago.fecha_pago = fecha_pago
        pago.monto_estimado = gasto.monto_estimado_decimal()
        pago.monto_pagado = monto_pagado
        pago.estado = 'pagado'
        pago.pagado_desde_caja = bool(pagado_desde_caja)
        pago.id_sesion_caja = sesion_caja.id_sesion if sesion_caja else None
        pago.id_usuario = current_user.id_usuario
        pago.observacion = observacion or None
        pago.numero_comprobante = numero_comprobante or None
        pago.id_movimiento_caja = None
        pago.id_movimiento_reversa = None
        pago.motivo_anulacion = None
        pago.fecha_anulacion = None
        pago.id_usuario_anulacion = None
        db.session.flush()

    movimiento = None
    if sesion_caja:
        movimiento = MovimientoCaja(
            id_sesion_caja=sesion_caja.id_sesion,
            id_usuario=current_user.id_usuario,
            tipo='egreso',
            monto=monto_pagado,
            motivo=f'Pago gasto corriente: {gasto.nombre}',
            referencia_tipo='gasto_corriente',
            referencia_id=pago.id_pago_gasto_corriente,
            fecha_movimiento=_fecha_pago_movimiento(fecha_pago),
        )
        db.session.add(movimiento)
        db.session.flush()
        pago.id_movimiento_caja = movimiento.id_movimiento_caja

    return pago, movimiento


def revertir_pago_gasto(
    pago: PagoGastoCorriente,
    *,
    motivo_anulacion: str | None,
) -> MovimientoCaja | None:
    if pago.esta_anulado():
        raise ValueError('El pago ya fue anulado.')

    movimiento_reversa = None
    if pago.pagado_desde_caja:
        sesion_reversa = _obtener_sesion_abierta_para_pago()
        if not sesion_reversa:
            raise ValueError('Abra una caja para revertir un pago que impactó efectivo.')
        movimiento_reversa = MovimientoCaja(
            id_sesion_caja=sesion_reversa.id_sesion,
            id_usuario=current_user.id_usuario,
            tipo='ingreso',
            monto=pago.monto_pagado_decimal(),
            motivo=f'Reversa gasto corriente: {pago.gasto_corriente.nombre}',
            referencia_tipo='gasto_corriente_reversa',
            referencia_id=pago.id_pago_gasto_corriente,
        )
        db.session.add(movimiento_reversa)
        db.session.flush()
        pago.id_movimiento_reversa = movimiento_reversa.id_movimiento_caja

    pago.estado = 'anulado'
    pago.fecha_anulacion = date.today()
    pago.id_usuario_anulacion = current_user.id_usuario
    pago.motivo_anulacion = (motivo_anulacion or '').strip() or None
    return movimiento_reversa
