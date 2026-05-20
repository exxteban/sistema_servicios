from __future__ import annotations

from datetime import datetime, time

from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    Compra,
    CuentaPorCobrar,
    MetodoPago,
    PagoCompra,
    PagoCuentaCobrar,
    PagoVenta,
    Venta,
)
from app.routes.caja.common import _resumenes_compras_por_ids, _resumenes_ventas_por_ids


def _money(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _datetime_from_date(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        return datetime.combine(value, time.min)
    return datetime.min


def _format_categoria(nombre: str | None) -> str:
    texto = (nombre or '').strip().replace('_', ' ')
    return texto.title() if texto else 'Sin categoría'


def _construir_detalle_pago_gasto(pago):
    gasto = getattr(pago, 'gasto_corriente', None)
    nombre = (getattr(gasto, 'nombre', '') or '').strip() or 'Gasto corriente'
    categoria = _format_categoria(getattr(gasto, 'categoria', None))
    estado = (pago.estado or '').strip().lower()
    detalle_partes = [f'Categoría: {categoria}', f'Período: {pago.periodo_mes:02d}/{pago.periodo_anio:04d}']
    if getattr(pago, 'numero_comprobante', None):
        detalle_partes.append(f'Comprobante: {pago.numero_comprobante}')
    if getattr(pago, 'observacion', None):
        detalle_partes.append((pago.observacion or '').strip())
    if estado == 'anulado':
        detalle_partes.append('Estado: anulado')

    return {
        'fecha': _datetime_from_date(pago.fecha_pago),
        'concepto': 'Gasto Corriente' if estado != 'anulado' else 'Gasto Corriente (Anulado)',
        'referencia': nombre,
        'forma_pago': 'Caja' if pago.pagado_desde_caja else 'Fuera de caja',
        'entrada': 0.0,
        'salida': _money(pago.monto_pagado),
        'detalle': ' | '.join(part for part in detalle_partes if part),
    }


def construir_detalles_contables(
    *,
    pagos_gastos,
    ventas_emitidas_rows,
    ventas_anuladas,
    anulaciones_pagos_rows,
    anulacion_fecha_por_venta,
    metodos_por_id,
    movimientos,
    start_utc: datetime,
    end_utc: datetime,
):
    detalles = [_construir_detalle_pago_gasto(pago) for pago in pagos_gastos]

    pagos_ventas_detalle = (
        db.session.query(PagoVenta, Venta, MetodoPago)
        .join(Venta, PagoVenta.id_venta == Venta.id_venta)
        .outerjoin(MetodoPago, PagoVenta.id_metodo_pago == MetodoPago.id_metodo_pago)
        .options(joinedload(Venta.cliente))
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
        )
        .order_by(Venta.fecha_venta.asc(), PagoVenta.id_pago.asc())
        .all()
    )
    resumenes_ventas = _resumenes_ventas_por_ids(
        {int(venta.id_venta) for _, venta, _ in pagos_ventas_detalle}.union(ventas_anuladas.keys())
    )
    cobrado_en_venta_por_id = {}
    for pago, venta, _ in pagos_ventas_detalle:
        venta_id = int(venta.id_venta)
        cobrado_en_venta_por_id[venta_id] = cobrado_en_venta_por_id.get(venta_id, 0.0) + _money(pago.monto)

    for venta in ventas_emitidas_rows:
        venta_id = int(venta.id_venta)
        tipo_venta = (venta.tipo_venta or 'contado').strip().lower()
        saldo_venta = _money(getattr(venta, 'saldo_pendiente', 0))
        cobrado_venta = cobrado_en_venta_por_id.get(venta_id, 0.0)
        detalle_partes = [
            f'Cliente: {getattr(getattr(venta, "cliente", None), "nombre", "") or "Consumidor Final"}',
            f'Tipo: {"Credito" if tipo_venta == "credito" else "Contado"}',
            f'Cobrado al momento: Gs. {cobrado_venta:,.0f}'.replace(',', '.'),
        ]
        if saldo_venta > 0:
            detalle_partes.append(f'Saldo financiado: Gs. {saldo_venta:,.0f}'.replace(',', '.'))
        descuento_manual = _money(getattr(venta, 'descuento_manual_monto', 0))
        descuento_fidelizacion = _money(getattr(venta, 'descuento_fidelizacion_monto', 0))
        beneficio_texto = (getattr(venta, 'beneficio_fidelizacion_descripcion', '') or '').strip()
        if descuento_manual > 0:
            detalle_partes.append(f'Descuento manual: Gs. {descuento_manual:,.0f}'.replace(',', '.'))
        if descuento_fidelizacion > 0:
            detalle_partes.append(f'Fidelización aplicada: Gs. {descuento_fidelizacion:,.0f}'.replace(',', '.'))
            if beneficio_texto:
                detalle_partes.append(f'Beneficio: {beneficio_texto}')
        detalles.append(
            {
                'fecha': venta.fecha_venta,
                'concepto': 'Venta Emitida',
                'referencia': f'Venta #{venta.id_venta}',
                'forma_pago': 'Credito' if tipo_venta == 'credito' else 'Contado',
                'entrada': 0.0,
                'salida': 0.0,
                'detalle': ' | '.join(detalle_partes),
            }
        )

    for pago, venta, metodo in pagos_ventas_detalle:
        tipo_venta = (venta.tipo_venta or 'contado').strip().lower()
        saldo_venta = _money(getattr(venta, 'saldo_pendiente', 0))
        detalle_partes = [resumenes_ventas.get(int(venta.id_venta), '')]
        detalle_partes.append(f'Tipo: {"Credito" if tipo_venta == "credito" else "Contado"}')
        if saldo_venta > 0:
            detalle_partes.append(f'Saldo financiado: Gs. {saldo_venta:,.0f}'.replace(',', '.'))
        forma_pago = metodo.nombre if metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
        detalles.append(
            {
                'fecha': venta.fecha_venta,
                'concepto': 'Cobro en Venta',
                'referencia': f'Venta #{venta.id_venta}',
                'forma_pago': forma_pago,
                'entrada': _money(pago.monto),
                'salida': 0.0,
                'detalle': ' | '.join(part for part in detalle_partes if part),
            }
        )

    for row in anulaciones_pagos_rows:
        venta = ventas_anuladas.get(int(row.id_venta))
        if not venta:
            continue
        fecha_anulacion = anulacion_fecha_por_venta.get(int(venta.id_venta)) or venta.fecha_venta
        metodo = metodos_por_id.get(int(row.id_metodo_pago))
        detalles.append(
            {
                'fecha': fecha_anulacion,
                'concepto': 'Anulación de Venta',
                'referencia': f'Venta #{venta.id_venta}',
                'forma_pago': metodo.nombre if metodo else f'Método #{int(row.id_metodo_pago or 0)}',
                'entrada': 0.0,
                'salida': _money(row.total),
                'detalle': resumenes_ventas.get(int(venta.id_venta), ''),
            }
        )

    pagos_creditos_detalle = (
        db.session.query(PagoCuentaCobrar, CuentaPorCobrar, MetodoPago)
        .join(CuentaPorCobrar, PagoCuentaCobrar.id_cuenta_cobrar == CuentaPorCobrar.id_cuenta_cobrar)
        .outerjoin(MetodoPago, PagoCuentaCobrar.id_metodo_pago == MetodoPago.id_metodo_pago)
        .filter(
            PagoCuentaCobrar.fecha_pago >= start_utc,
            PagoCuentaCobrar.fecha_pago < end_utc,
            PagoCuentaCobrar.estado != 'anulado',
        )
        .order_by(PagoCuentaCobrar.fecha_pago.asc(), PagoCuentaCobrar.id_pago_cuenta.asc())
        .all()
    )
    for pago, cuenta, metodo in pagos_creditos_detalle:
        referencia = f'Cuenta #{cuenta.id_cuenta_cobrar}'
        if cuenta.id_venta:
            referencia = f'Venta #{cuenta.id_venta} (Cuenta #{cuenta.id_cuenta_cobrar})'
        forma_pago = metodo.nombre if metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
        detalles.append(
            {
                'fecha': pago.fecha_pago,
                'concepto': 'Cobro de Crédito',
                'referencia': referencia,
                'forma_pago': forma_pago,
                'entrada': _money(pago.monto),
                'salida': 0.0,
                'detalle': '',
            }
        )

    pagos_compras_detalle = (
        db.session.query(PagoCompra, Compra, MetodoPago)
        .join(Compra, PagoCompra.id_compra == Compra.id_compra)
        .outerjoin(MetodoPago, PagoCompra.id_metodo_pago == MetodoPago.id_metodo_pago)
        .filter(
            PagoCompra.fecha_pago >= start_utc,
            PagoCompra.fecha_pago < end_utc,
        )
        .order_by(PagoCompra.fecha_pago.asc(), PagoCompra.id_pago_compra.asc())
        .all()
    )
    resumenes_compras = _resumenes_compras_por_ids(int(compra.id_compra) for _, compra, _ in pagos_compras_detalle)
    for pago, compra, metodo in pagos_compras_detalle:
        forma_pago = metodo.nombre if metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
        detalles.append(
            {
                'fecha': pago.fecha_pago,
                'concepto': 'Pago de Compra',
                'referencia': f'Compra #{pago.id_compra}',
                'forma_pago': forma_pago,
                'entrada': 0.0,
                'salida': _money(pago.monto),
                'detalle': resumenes_compras.get(int(compra.id_compra), ''),
            }
        )

    for mov in movimientos:
        referencia_tipo = (mov.referencia_tipo or '').strip().lower()
        if referencia_tipo == 'compra':
            continue
        if mov.tipo == 'egreso' and referencia_tipo == 'anulacion_venta':
            continue
        if mov.tipo == 'ingreso' and referencia_tipo in {'venta', 'cobro_credito'}:
            continue
        if referencia_tipo == 'gasto_corriente':
            continue

        detalles.append(
            {
                'fecha': mov.fecha_movimiento,
                'concepto': 'Reversa Gasto Corriente' if referencia_tipo == 'gasto_corriente_reversa' else 'Movimiento de Caja',
                'referencia': getattr(mov, 'motivo_detallado', None) or mov.motivo,
                'forma_pago': 'Efectivo',
                'entrada': _money(mov.monto) if mov.tipo == 'ingreso' else 0.0,
                'salida': _money(mov.monto) if mov.tipo == 'egreso' else 0.0,
                'detalle': '',
            }
        )

    detalles.sort(key=lambda row: (row['fecha'] or datetime.min, row['concepto'], row['referencia']))
    return detalles
