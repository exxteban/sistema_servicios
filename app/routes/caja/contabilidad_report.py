from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    Auditoria,
    CuentaPorCobrar,
    MetodoPago,
    MovimientoCaja,
    PagoCompra,
    PagoCuentaCobrar,
    PagoVenta,
    Venta,
)
from app.routes.caja.common import (
    _enriquecer_motivos_movimientos,
    _resolver_metodo_efectivo_id,
)
from app.routes.caja.contabilidad_detalles import construir_detalles_contables
from cobranzas.models import PlanCreditoVenta
from gastos_corrientes.models import PagoGastoCorriente
from gastos_corrientes.services.gasto_corriente_service import aplicar_scope_cliente


def _money(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _format_categoria(nombre: str | None) -> str:
    texto = (nombre or '').strip().replace('_', ' ')
    return texto.title() if texto else 'Sin categoría'


def _consultar_pagos_gastos_corrientes(start_utc: datetime, end_utc: datetime):
    return (
        aplicar_scope_cliente(PagoGastoCorriente.query, PagoGastoCorriente)
        .options(joinedload(PagoGastoCorriente.gasto_corriente))
        .filter(
            PagoGastoCorriente.fecha_pago.isnot(None),
            PagoGastoCorriente.fecha_pago >= start_utc.date(),
            PagoGastoCorriente.fecha_pago < end_utc.date(),
        )
        .order_by(
            PagoGastoCorriente.fecha_pago.asc(),
            PagoGastoCorriente.id_pago_gasto_corriente.asc(),
        )
        .all()
    )


def _enriquecer_movimientos_gastos_corrientes(movimientos, pagos_por_id):
    for mov in movimientos:
        referencia_tipo = (getattr(mov, 'referencia_tipo', '') or '').strip().lower()
        if referencia_tipo not in {'gasto_corriente', 'gasto_corriente_reversa'}:
            continue

        pago = pagos_por_id.get(int(getattr(mov, 'referencia_id', 0) or 0))
        if not pago:
            continue

        gasto = getattr(pago, 'gasto_corriente', None)
        nombre = (getattr(gasto, 'nombre', '') or '').strip() or 'Gasto corriente'
        categoria = _format_categoria(getattr(gasto, 'categoria', None))
        periodo = f'{int(pago.periodo_mes or 0):02d}/{int(pago.periodo_anio or 0):04d}'
        base = (getattr(mov, 'motivo', '') or '').strip()
        partes = [f'Categoría: {categoria}', f'Período: {periodo}']
        if getattr(pago, 'numero_comprobante', None):
            partes.append(f'Comprobante: {pago.numero_comprobante}')
        detalle = ' | '.join(partes)
        motivo = f'{base} ({nombre})' if base and nombre not in base else (base or nombre)
        setattr(mov, 'motivo_detallado', f'{motivo} - {detalle}'.strip(' -'))


def _clasificar_movimientos(movimientos):
    totales = {
        'mov_ingresos': 0.0,
        'mov_egresos': 0.0,
        'ventas_efectivo_mov': 0.0,
        'vuelto': 0.0,
        'reembolsos': 0.0,
        'ingresos_varios': 0.0,
        'egresos_varios': 0.0,
        'gastos_corrientes_caja': 0.0,
        'reversas_gastos_corrientes': 0.0,
    }

    for mov in movimientos:
        monto = _money(mov.monto)
        referencia_tipo = (mov.referencia_tipo or '').strip().lower()
        if mov.tipo == 'egreso' and referencia_tipo == 'compra':
            continue
        if mov.tipo == 'egreso' and referencia_tipo == 'anulacion_venta':
            continue
        if mov.tipo == 'ingreso' and referencia_tipo == 'cobro_credito':
            continue

        if mov.tipo == 'ingreso':
            totales['mov_ingresos'] += monto
            if referencia_tipo == 'venta':
                totales['ventas_efectivo_mov'] += monto
            elif referencia_tipo == 'gasto_corriente_reversa':
                totales['reversas_gastos_corrientes'] += monto
            else:
                totales['ingresos_varios'] += monto
            continue

        totales['mov_egresos'] += monto
        motivo = (mov.motivo or '').strip().lower()
        if referencia_tipo == 'gasto_corriente':
            totales['gastos_corrientes_caja'] += monto
        elif referencia_tipo == 'vuelto' or (referencia_tipo == 'venta' and motivo.startswith('vuelto')):
            # Tolerante: acepta referencia_tipo='vuelto' (nuevo) y el formato
            # histórico referencia_tipo='venta' + motivo que empieza con 'vuelto'.
            totales['vuelto'] += monto
        elif referencia_tipo == 'devolucion':
            totales['reembolsos'] += monto
        else:
            totales['egresos_varios'] += monto

    return totales


def calcular_informe_contable_rango(start_utc: datetime, end_utc: datetime):
    metodos = (
        MetodoPago.query
        .order_by(MetodoPago.orden_display.asc(), MetodoPago.nombre.asc())
        .all()
    )
    metodos_por_id = {m.id_metodo_pago: m for m in metodos}

    ventas_emitidas_rows = (
        Venta.query.options(joinedload(Venta.cliente))
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
        )
        .order_by(Venta.fecha_venta.asc(), Venta.id_venta.asc())
        .all()
    )
    ventas_emitidas_por_id = {int(v.id_venta): v for v in ventas_emitidas_rows}

    pagos_ventas_agg_rows = (
        db.session.query(
            PagoVenta.id_metodo_pago,
            func.sum(PagoVenta.monto).label('total'),
            func.count(PagoVenta.id_pago).label('cantidad'),
        )
        .join(Venta, PagoVenta.id_venta == Venta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
        )
        .group_by(PagoVenta.id_metodo_pago)
        .all()
    )
    pagos_ventas_agg = {int(r.id_metodo_pago): r for r in pagos_ventas_agg_rows}

    pagos_creditos_agg_rows = (
        db.session.query(
            PagoCuentaCobrar.id_metodo_pago,
            func.sum(PagoCuentaCobrar.monto).label('total'),
            func.count(PagoCuentaCobrar.id_pago_cuenta).label('cantidad'),
        )
        .filter(
            PagoCuentaCobrar.fecha_pago >= start_utc,
            PagoCuentaCobrar.fecha_pago < end_utc,
            PagoCuentaCobrar.estado != 'anulado',
        )
        .group_by(PagoCuentaCobrar.id_metodo_pago)
        .all()
    )
    pagos_creditos_agg = {int(r.id_metodo_pago): r for r in pagos_creditos_agg_rows}

    pagos_compras_agg_rows = (
        db.session.query(
            PagoCompra.id_metodo_pago,
            func.sum(PagoCompra.monto).label('total'),
            func.count(PagoCompra.id_pago_compra).label('cantidad'),
        )
        .filter(
            PagoCompra.fecha_pago >= start_utc,
            PagoCompra.fecha_pago < end_utc,
        )
        .group_by(PagoCompra.id_metodo_pago)
        .all()
    )
    pagos_compras_agg = {int(r.id_metodo_pago): r for r in pagos_compras_agg_rows}

    anulaciones_auditoria = (
        db.session.query(Auditoria.referencia_id, Auditoria.fecha_accion)
        .filter(
            Auditoria.accion == 'anular_venta',
            Auditoria.modulo == 'ventas',
            Auditoria.referencia_tipo == 'venta',
            Auditoria.referencia_id.isnot(None),
            Auditoria.fecha_accion >= start_utc,
            Auditoria.fecha_accion < end_utc,
        )
        .order_by(Auditoria.fecha_accion.asc(), Auditoria.id_auditoria.asc())
        .all()
    )
    anulacion_fecha_por_venta = {}
    venta_ids_anuladas = []
    for ref_id, fecha_accion in anulaciones_auditoria:
        try:
            venta_id = int(ref_id)
        except Exception:
            continue
        if venta_id not in anulacion_fecha_por_venta:
            anulacion_fecha_por_venta[venta_id] = fecha_accion
            venta_ids_anuladas.append(venta_id)

    anulaciones_pagos_rows = []
    ventas_anuladas = {}
    anulaciones_por_metodo = {}
    if venta_ids_anuladas:
        anulaciones_pagos_rows = (
            db.session.query(PagoVenta.id_venta, PagoVenta.id_metodo_pago, func.sum(PagoVenta.monto).label('total'))
            .filter(PagoVenta.id_venta.in_(sorted(set(venta_ids_anuladas))))
            .group_by(PagoVenta.id_venta, PagoVenta.id_metodo_pago)
            .all()
        )
        ventas_anuladas_rows = (
            Venta.query.options(joinedload(Venta.cliente))
            .filter(Venta.id_venta.in_(sorted(set(venta_ids_anuladas))))
            .all()
        )
        ventas_anuladas = {int(v.id_venta): v for v in ventas_anuladas_rows}
        for row in anulaciones_pagos_rows:
            try:
                metodo_id = int(row.id_metodo_pago)
            except Exception:
                continue
            anulaciones_por_metodo[metodo_id] = _money(anulaciones_por_metodo.get(metodo_id)) + _money(row.total)

    total_anulaciones_comerciales = sum(_money(getattr(v, 'total', 0)) for v in ventas_anuladas.values())
    descuentos_manuales_ventas = sum(_money(getattr(v, 'descuento_manual_monto', 0)) for v in ventas_emitidas_rows)
    descuentos_fidelizacion_ventas = sum(_money(getattr(v, 'descuento_fidelizacion_monto', 0)) for v in ventas_emitidas_rows)
    saldo_favor_fidelizacion_aplicado = sum(
        _money(getattr(v, 'descuento_fidelizacion_monto', 0))
        for v in ventas_emitidas_rows
        if (getattr(v, 'beneficio_fidelizacion_tipo', '') or '').strip() == 'saldo_favor'
    )

    saldo_financiado_generado = (
        db.session.query(func.coalesce(func.sum(CuentaPorCobrar.monto_total), 0))
        .join(Venta, CuentaPorCobrar.id_venta == Venta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
        )
        .scalar()
    )
    saldo_financiado_generado = _money(saldo_financiado_generado)

    interes_financiero_generado = (
        db.session.query(func.coalesce(func.sum(PlanCreditoVenta.monto_total_interes), 0))
        .join(CuentaPorCobrar, PlanCreditoVenta.id_cuenta_cobrar == CuentaPorCobrar.id_cuenta_cobrar)
        .join(Venta, CuentaPorCobrar.id_venta == Venta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
        )
        .scalar()
    )
    interes_financiero_generado = _money(interes_financiero_generado)

    movimientos = (
        MovimientoCaja.query.options(joinedload(MovimientoCaja.usuario))
        .filter(
            MovimientoCaja.fecha_movimiento >= start_utc,
            MovimientoCaja.fecha_movimiento < end_utc,
        )
        .order_by(MovimientoCaja.fecha_movimiento.asc(), MovimientoCaja.id_movimiento_caja.asc())
        .all()
    )

    pagos_gastos = _consultar_pagos_gastos_corrientes(start_utc, end_utc)
    pagos_gastos_por_id = {int(p.id_pago_gasto_corriente): p for p in pagos_gastos}
    pagos_gastos_activos = [p for p in pagos_gastos if not p.esta_anulado()]

    _enriquecer_motivos_movimientos(movimientos)
    _enriquecer_movimientos_gastos_corrientes(movimientos, pagos_gastos_por_id)
    totales_mov = _clasificar_movimientos(movimientos)

    ventas_por_metodo = []
    creditos_por_metodo = []
    compras_por_metodo = []

    for metodo in metodos:
        total_venta = pagos_ventas_agg.get(metodo.id_metodo_pago)
        total_credito = pagos_creditos_agg.get(metodo.id_metodo_pago)
        total_compra = pagos_compras_agg.get(metodo.id_metodo_pago)
        ventas_por_metodo.append(
            {
                'id_metodo_pago': metodo.id_metodo_pago,
                'nombre': metodo.nombre,
                'total': _money(total_venta.total) if total_venta else 0.0,
                'cantidad': int(total_venta.cantidad) if total_venta and total_venta.cantidad else 0,
            }
        )
        creditos_por_metodo.append(
            {
                'id_metodo_pago': metodo.id_metodo_pago,
                'nombre': metodo.nombre,
                'total': _money(total_credito.total) if total_credito else 0.0,
                'cantidad': int(total_credito.cantidad) if total_credito and total_credito.cantidad else 0,
            }
        )
        compras_por_metodo.append(
            {
                'id_metodo_pago': metodo.id_metodo_pago,
                'nombre': metodo.nombre,
                'total': _money(total_compra.total) if total_compra else 0.0,
                'cantidad': int(total_compra.cantidad) if total_compra and total_compra.cantidad else 0,
            }
        )

    efectivo_id = _resolver_metodo_efectivo_id(metodos, metodos_por_id)

    ventas_efectivo = 0.0
    for item in ventas_por_metodo:
        if efectivo_id is not None and item['id_metodo_pago'] == efectivo_id:
            ventas_efectivo = item['total']
            break
    if ventas_efectivo <= 0:
        ventas_efectivo = totales_mov['ventas_efectivo_mov']

    ventas_emitidas = sum(_money(getattr(venta, 'total', 0)) for venta in ventas_emitidas_rows)
    cobrado_en_ventas = sum(item['total'] for item in ventas_por_metodo)
    total_cobros_creditos = sum(item['total'] for item in creditos_por_metodo)
    total_pagos_compras = sum(item['total'] for item in compras_por_metodo)
    total_anulaciones = sum(_money(value) for value in anulaciones_por_metodo.values())
    facturacion_real = ventas_emitidas - total_anulaciones_comerciales
    total_gastos_corrientes = sum(_money(pago.monto_pagado) for pago in pagos_gastos_activos)
    total_gastos_corrientes_fuera_caja = sum(
        _money(pago.monto_pagado) for pago in pagos_gastos_activos if not pago.pagado_desde_caja
    )

    total_ingresos = cobrado_en_ventas + total_cobros_creditos + totales_mov['ingresos_varios'] + totales_mov['reversas_gastos_corrientes']
    total_egresos = total_pagos_compras + totales_mov['mov_egresos'] + total_anulaciones
    resultado_caja_mes = total_ingresos - total_egresos

    ingresos_operativos = facturacion_real + interes_financiero_generado
    egresos_operativos = total_pagos_compras + totales_mov['reembolsos'] + totales_mov['egresos_varios'] + total_gastos_corrientes
    ganancia_neta_mes = ingresos_operativos - egresos_operativos

    conceptos = []
    conceptos_no_caja = []
    if ventas_efectivo:
        conceptos.append({'concepto': 'Cobrado en Ventas - Efectivo', 'entrada': ventas_efectivo, 'salida': 0.0})

    if descuentos_manuales_ventas:
        conceptos_no_caja.append({'concepto': 'Descuentos manuales sobre ventas', 'monto': descuentos_manuales_ventas})
    if descuentos_fidelizacion_ventas:
        conceptos_no_caja.append({'concepto': 'Descuentos por fidelización', 'monto': descuentos_fidelizacion_ventas})
    if saldo_favor_fidelizacion_aplicado:
        conceptos_no_caja.append({'concepto': 'Saldo a favor aplicado (fidelización)', 'monto': saldo_favor_fidelizacion_aplicado})

    for venta in ventas_por_metodo:
        if efectivo_id is not None and venta['id_metodo_pago'] == efectivo_id:
            continue
        if venta['total']:
            conceptos.append({'concepto': f'Cobrado en Ventas - {venta["nombre"]}', 'entrada': venta['total'], 'salida': 0.0})

    for metodo in metodos:
        metodo_id = int(metodo.id_metodo_pago)
        total_anulado = _money(anulaciones_por_metodo.get(metodo_id, 0.0))
        if total_anulado:
            conceptos.append({'concepto': f'Anulaciones - {metodo.nombre}', 'entrada': 0.0, 'salida': total_anulado})

    for credito in creditos_por_metodo:
        if credito['total']:
            conceptos.append({'concepto': f'Cobros de Créditos - {credito["nombre"]}', 'entrada': credito['total'], 'salida': 0.0})

    if totales_mov['ingresos_varios']:
        conceptos.append(
            {'concepto': 'Ingresos Manuales / Ajustes', 'entrada': totales_mov['ingresos_varios'], 'salida': 0.0}
        )
    if totales_mov['reversas_gastos_corrientes']:
        conceptos.append(
            {
                'concepto': 'Reversas de Gastos Corrientes',
                'entrada': totales_mov['reversas_gastos_corrientes'],
                'salida': 0.0,
            }
        )

    if total_pagos_compras:
        for compra in compras_por_metodo:
            if compra['total']:
                conceptos.append(
                    {'concepto': f'Pagos de Compras - {compra["nombre"]}', 'entrada': 0.0, 'salida': compra['total']}
                )

    if totales_mov['gastos_corrientes_caja']:
        conceptos.append(
            {
                'concepto': 'Gastos Corrientes (Caja)',
                'entrada': 0.0,
                'salida': totales_mov['gastos_corrientes_caja'],
            }
        )
    if totales_mov['vuelto']:
        conceptos.append({'concepto': 'Vuelto', 'entrada': 0.0, 'salida': totales_mov['vuelto']})
    if totales_mov['reembolsos']:
        conceptos.append({'concepto': 'Reembolsos', 'entrada': 0.0, 'salida': totales_mov['reembolsos']})
    if totales_mov['egresos_varios']:
        conceptos.append({'concepto': 'Egresos Varios', 'entrada': 0.0, 'salida': totales_mov['egresos_varios']})

    detalles = construir_detalles_contables(
        pagos_gastos=pagos_gastos,
        ventas_emitidas_rows=ventas_emitidas_rows,
        ventas_anuladas=ventas_anuladas,
        anulaciones_pagos_rows=anulaciones_pagos_rows,
        anulacion_fecha_por_venta=anulacion_fecha_por_venta,
        metodos_por_id=metodos_por_id,
        movimientos=movimientos,
        start_utc=start_utc,
        end_utc=end_utc,
    )

    return {
        'ventas_por_metodo': ventas_por_metodo,
        'creditos_por_metodo': creditos_por_metodo,
        'compras_por_metodo': compras_por_metodo,
        'movimientos': movimientos,
        'conceptos': conceptos,
        'conceptos_no_caja': conceptos_no_caja,
        'detalles': detalles,
        'total_ingresos': total_ingresos,
        'total_egresos': total_egresos,
        'neto': resultado_caja_mes,
        'resultado_caja_mes': resultado_caja_mes,
        'ganancia_neta_mes': ganancia_neta_mes,
        'ingresos_operativos': ingresos_operativos,
        'egresos_operativos': egresos_operativos,
        'ingresos_manuales': totales_mov['ingresos_varios'],
        'gastos_corrientes_mes': total_gastos_corrientes,
        'gastos_corrientes_fuera_caja': total_gastos_corrientes_fuera_caja,
        'reversas_gastos_corrientes': totales_mov['reversas_gastos_corrientes'],
        'ventas_emitidas': ventas_emitidas,
        'descuentos_manuales_ventas': descuentos_manuales_ventas,
        'descuentos_fidelizacion_ventas': descuentos_fidelizacion_ventas,
        'saldo_favor_fidelizacion_aplicado': saldo_favor_fidelizacion_aplicado,
        'cobrado_en_ventas': cobrado_en_ventas,
        'saldo_financiado_generado': saldo_financiado_generado,
        'interes_financiero_generado': interes_financiero_generado,
        'total_anulaciones_comerciales': total_anulaciones_comerciales,
        'total_ventas': cobrado_en_ventas,
        'facturacion_real': facturacion_real,
        'total_cobros_creditos': total_cobros_creditos,
        'total_pagos_compras': total_pagos_compras,
        'efectivo_id': efectivo_id,
    }
