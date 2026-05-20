from __future__ import annotations

from datetime import datetime

from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    Compra,
    CuentaPorCobrar,
    DetalleCompra,
    DetalleVenta,
    MetodoPago,
    MovimientoCaja,
    PedidoClientePago,
    PagoCompra,
    PagoCuentaCobrar,
    PagoVenta,
    PedidoCliente,
    SesionCaja,
    Venta,
)
from app.routes.caja.detalle_utils import (
    _descripcion_compra_detalle,
    _descripcion_venta_detalle,
    _enriquecer_motivos_movimientos,
    _resumen_productos,
    _resumenes_compras_por_ids,
    _resumenes_ventas_por_ids,
)
from app.services.caja_cuadre import obtener_resumen_anulaciones_ventas_sesion


def _puede_ver_sesion(sesion: SesionCaja) -> bool:
    if current_user.es_admin():
        return True
    if current_user.tiene_permiso('ver_otras_cajas'):
        return True
    return sesion.id_usuario == current_user.id_usuario or sesion.id_usuario_cierre == current_user.id_usuario


def _norm_metodo_pago_nombre(nombre: str) -> str:
    s = (nombre or '').strip().lower()
    s = s.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
    return ' '.join(s.split())


def _resolver_metodo_efectivo_id(metodos, metodos_por_id):
    """
    Wrapper de compatibilidad. Delega en `app.services.caja_metodos`.
    Se mantiene la firma para no romper call sites existentes.
    """
    from app.services.caja_metodos import obtener_metodo_efectivo_id

    return obtener_metodo_efectivo_id(metodos)


def _calcular_informe_cierre_sesion(sesion: SesionCaja):
    id_sesion = sesion.id_sesion

    metodos = (
        MetodoPago.query.filter_by(activo=True)
        .order_by(MetodoPago.orden_display.asc(), MetodoPago.nombre.asc())
        .all()
    )
    metodos_por_id = {m.id_metodo_pago: m for m in metodos}
    efectivo_id = _resolver_metodo_efectivo_id(metodos, metodos_por_id)

    pagos_ventas_agg_rows = (
        db.session.query(
            PagoVenta.id_metodo_pago,
            func.sum(PagoVenta.monto).label('total'),
            func.count(PagoVenta.id_pago).label('cantidad'),
        )
        .join(Venta, PagoVenta.id_venta == Venta.id_venta)
        .filter(Venta.id_sesion_caja == id_sesion, Venta.estado == 'completada')
        .group_by(PagoVenta.id_metodo_pago)
        .all()
    )
    pagos_ventas_agg = {int(r.id_metodo_pago): r for r in pagos_ventas_agg_rows}

    anulaciones_ctx = obtener_resumen_anulaciones_ventas_sesion(sesion, efectivo_id=efectivo_id)
    anulacion_fecha_por_venta = anulaciones_ctx['fecha_por_venta']
    anulaciones_pagos_rows = anulaciones_ctx['pagos_rows']
    ventas_anuladas = anulaciones_ctx['ventas_por_id']
    anulaciones_por_metodo = anulaciones_ctx['mostrado_por_metodo']
    anulaciones_efectivo_esperado = float(anulaciones_ctx['efectivo_esperado'] or 0.0)
    anulaciones_efectivo_mov = float(anulaciones_ctx['efectivo_movimientos'] or 0.0)

    pagos_creditos_agg_rows = (
        db.session.query(
            PagoCuentaCobrar.id_metodo_pago,
            func.sum(PagoCuentaCobrar.monto).label('total'),
            func.count(PagoCuentaCobrar.id_pago_cuenta).label('cantidad'),
        )
        .filter(
            PagoCuentaCobrar.id_sesion_caja == id_sesion,
            PagoCuentaCobrar.estado != 'anulado',
        )
        .group_by(PagoCuentaCobrar.id_metodo_pago)
        .all()
    )
    pagos_creditos_agg = {int(r.id_metodo_pago): r for r in pagos_creditos_agg_rows}

    pagos_pedidos_agg_rows = (
        db.session.query(
            PedidoClientePago.id_metodo_pago,
            func.sum(PedidoClientePago.monto).label('total'),
            func.count(PedidoClientePago.id_pago_pedido).label('cantidad'),
        )
        .filter(
            PedidoClientePago.id_sesion_caja == id_sesion,
            PedidoClientePago.estado == 'activo',
        )
        .group_by(PedidoClientePago.id_metodo_pago)
        .all()
    )
    pagos_pedidos_agg = {int(r.id_metodo_pago): r for r in pagos_pedidos_agg_rows}

    pagos_compras_agg_rows = (
        db.session.query(
            PagoCompra.id_metodo_pago,
            func.sum(PagoCompra.monto).label('total'),
            func.count(PagoCompra.id_pago_compra).label('cantidad'),
        )
        .filter(PagoCompra.id_sesion_caja == id_sesion)
        .group_by(PagoCompra.id_metodo_pago)
        .all()
    )
    pagos_compras_agg = {int(r.id_metodo_pago): r for r in pagos_compras_agg_rows}

    movimientos = (
        MovimientoCaja.query.options(joinedload(MovimientoCaja.usuario))
        .filter(MovimientoCaja.id_sesion_caja == id_sesion)
        .order_by(MovimientoCaja.fecha_movimiento.asc(), MovimientoCaja.id_movimiento_caja.asc())
        .all()
    )
    _enriquecer_motivos_movimientos(movimientos)

    def _money(x):
        try:
            return float(x or 0)
        except Exception:
            return 0.0

    monto_inicial = _money(sesion.monto_inicial)

    mov_ingresos = 0.0
    mov_egresos = 0.0
    ventas_efectivo_mov = 0.0
    vuelto = 0.0
    reembolsos = 0.0
    ingresos_varios = 0.0
    egresos_varios = 0.0

    for mov in movimientos:
        monto = _money(mov.monto)
        referencia_tipo = (mov.referencia_tipo or '').strip().lower()
        if mov.tipo == 'egreso' and referencia_tipo == 'compra':
            continue
        if mov.tipo == 'egreso' and referencia_tipo == 'anulacion_venta':
            continue
        if mov.tipo == 'ingreso':
            mov_ingresos += monto
            if referencia_tipo == 'venta':
                ventas_efectivo_mov += monto
            else:
                ingresos_varios += monto
        else:
            mov_egresos += monto
            ref = referencia_tipo
            motivo = (mov.motivo or '').strip().lower()
            # Tolerante: acepta referencia_tipo='vuelto' (nuevo) y el formato
            # histórico referencia_tipo='venta' + motivo que empieza con 'vuelto'.
            if ref == 'vuelto' or (ref == 'venta' and motivo.startswith('vuelto')):
                vuelto += monto
            elif ref == 'devolucion':
                reembolsos += monto
            else:
                egresos_varios += monto

    ventas_por_metodo = []
    creditos_por_metodo = []
    pedidos_por_metodo = []
    compras_por_metodo = []

    for m in metodos:
        total_v = pagos_ventas_agg.get(m.id_metodo_pago)
        total_c = pagos_creditos_agg.get(m.id_metodo_pago)
        total_pd = pagos_pedidos_agg.get(m.id_metodo_pago)
        total_p = pagos_compras_agg.get(m.id_metodo_pago)
        ventas_por_metodo.append(
            {
                'id_metodo_pago': m.id_metodo_pago,
                'nombre': m.nombre,
                'total': _money(total_v.total) if total_v else 0.0,
                'cantidad': int(total_v.cantidad) if total_v and total_v.cantidad else 0,
            }
        )
        creditos_por_metodo.append(
            {
                'id_metodo_pago': m.id_metodo_pago,
                'nombre': m.nombre,
                'total': _money(total_c.total) if total_c else 0.0,
                'cantidad': int(total_c.cantidad) if total_c and total_c.cantidad else 0,
            }
        )
        pedidos_por_metodo.append(
            {
                'id_metodo_pago': m.id_metodo_pago,
                'nombre': m.nombre,
                'total': _money(total_pd.total) if total_pd else 0.0,
                'cantidad': int(total_pd.cantidad) if total_pd and total_pd.cantidad else 0,
            }
        )
        compras_por_metodo.append(
            {
                'id_metodo_pago': m.id_metodo_pago,
                'nombre': m.nombre,
                'total': _money(total_p.total) if total_p else 0.0,
                'cantidad': int(total_p.cantidad) if total_p and total_p.cantidad else 0,
            }
        )

    ventas_efectivo = 0.0
    for item in ventas_por_metodo:
        if efectivo_id is not None and item['id_metodo_pago'] == efectivo_id:
            ventas_efectivo = item['total']
            break
    if ventas_efectivo <= 0:
        ventas_efectivo = ventas_efectivo_mov

    total_ventas = sum(x['total'] for x in ventas_por_metodo)
    total_cobros_creditos = sum(x['total'] for x in creditos_por_metodo)
    total_cobros_pedidos = sum(x['total'] for x in pedidos_por_metodo)
    total_pagos_compras = sum(x['total'] for x in compras_por_metodo)
    total_anulaciones = sum(float(v or 0) for v in anulaciones_por_metodo.values())
    facturacion_real = total_ventas - vuelto

    total_ingresos = monto_inicial + total_ventas + total_cobros_creditos + total_cobros_pedidos + ingresos_varios
    total_egresos = total_pagos_compras + mov_egresos + total_anulaciones
    neto = total_ingresos - total_egresos

    try:
        total_efectivo_sistema = float(sesion.calcular_total_efectivo() or 0)
    except Exception:
        total_efectivo_sistema = _money(sesion.monto_final_sistema)
    ingreso_real_efectivo = total_efectivo_sistema - monto_inicial
    declarado = _money(sesion.monto_final_declarado)
    diferencia_efectivo = _money(sesion.diferencia)

    conceptos = []
    conceptos.append({'concepto': 'Caja Inicial', 'entrada': monto_inicial, 'salida': 0.0, 'key': 'caja_inicial'})
    if ventas_efectivo:
        ventas_efectivo_key = 'ventas_metodo' if efectivo_id is not None else 'ventas_efectivo_mov'
        conceptos.append(
            {
                'concepto': 'Ventas en Efectivo',
                'entrada': ventas_efectivo,
                'salida': 0.0,
                'key': ventas_efectivo_key,
                'metodo_id': efectivo_id,
            }
        )

    for v in ventas_por_metodo:
        if efectivo_id is not None and v['id_metodo_pago'] == efectivo_id:
            continue
        if v['total']:
            conceptos.append(
                {
                    'concepto': f'Ventas - {v["nombre"]}',
                    'entrada': v['total'],
                    'salida': 0.0,
                    'key': 'ventas_metodo',
                    'metodo_id': v['id_metodo_pago'],
                }
            )

    for m in metodos:
        mid = int(m.id_metodo_pago)
        total_anul = float(anulaciones_por_metodo.get(mid, 0.0) or 0.0)
        if total_anul:
            conceptos.append(
                {
                    'concepto': f'Anulaciones - {m.nombre}',
                    'entrada': 0.0,
                    'salida': total_anul,
                    'key': 'anulaciones_ventas_metodo',
                    'metodo_id': mid,
                }
            )

    for c in creditos_por_metodo:
        if c['total']:
            conceptos.append(
                {
                    'concepto': f'Cobros de Créditos - {c["nombre"]}',
                    'entrada': c['total'],
                    'salida': 0.0,
                    'key': 'cobros_creditos_metodo',
                    'metodo_id': c['id_metodo_pago'],
                }
            )

    for p in pedidos_por_metodo:
        if p['total']:
            conceptos.append(
                {
                    'concepto': f'Cobros de Pedidos - {p["nombre"]}',
                    'entrada': p['total'],
                    'salida': 0.0,
                    'key': 'cobros_pedidos_metodo',
                    'metodo_id': p['id_metodo_pago'],
                }
            )

    if ingresos_varios:
        conceptos.append({'concepto': 'Ingresos Varios', 'entrada': ingresos_varios, 'salida': 0.0, 'key': 'ingresos_varios'})

    if total_pagos_compras:
        for p in compras_por_metodo:
            if p['total']:
                conceptos.append(
                    {
                        'concepto': f'Pagos de Compras - {p["nombre"]}',
                        'entrada': 0.0,
                        'salida': p['total'],
                        'key': 'pagos_compras_metodo',
                        'metodo_id': p['id_metodo_pago'],
                    }
                )

    if vuelto:
        conceptos.append({'concepto': 'Vuelto', 'entrada': 0.0, 'salida': vuelto, 'key': 'vuelto'})
    if reembolsos:
        conceptos.append({'concepto': 'Reembolsos', 'entrada': 0.0, 'salida': reembolsos, 'key': 'reembolsos'})
    if egresos_varios:
        conceptos.append({'concepto': 'Egresos Varios', 'entrada': 0.0, 'salida': egresos_varios, 'key': 'egresos_varios'})

    detalles = []
    if sesion.fecha_apertura:
        detalles.append(
            {
                'fecha': sesion.fecha_apertura,
                'concepto': 'Caja Inicial',
                'referencia': f'Sesión #{sesion.id_sesion}',
                'forma_pago': 'Efectivo',
                'entrada': monto_inicial,
                'salida': 0.0,
                'detalle': '',
                'tx_tipo': 'sesion_apertura',
                'tx_id': int(sesion.id_sesion),
            }
        )

    pagos_ventas_detalle = (
        db.session.query(PagoVenta, Venta, MetodoPago)
        .join(Venta, PagoVenta.id_venta == Venta.id_venta)
        .outerjoin(MetodoPago, PagoVenta.id_metodo_pago == MetodoPago.id_metodo_pago)
        .options(joinedload(Venta.cliente))
        .filter(Venta.id_sesion_caja == id_sesion, Venta.estado == 'completada')
        .order_by(Venta.fecha_venta.asc(), PagoVenta.id_pago.asc())
        .all()
    )
    resumenes_ventas = _resumenes_ventas_por_ids(
        {int(venta.id_venta) for _, venta, _ in pagos_ventas_detalle}.union(ventas_anuladas.keys())
    )
    for pago, venta, metodo in pagos_ventas_detalle:
        descripcion = resumenes_ventas.get(int(venta.id_venta), '')
        forma_pago = metodo.nombre if metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
        detalles.append(
            {
                'fecha': venta.fecha_venta,
                'concepto': 'Venta',
                'referencia': f'Venta #{venta.id_venta}',
                'forma_pago': forma_pago,
                'entrada': _money(pago.monto),
                'salida': 0.0,
                'detalle': descripcion,
                'tx_tipo': 'venta',
                'tx_id': int(venta.id_venta),
                'tx_pago_id': int(pago.id_pago),
            }
        )

    usar_movimientos_efectivo_anulacion = (
        efectivo_id is not None
        and anulaciones_efectivo_mov >= anulaciones_efectivo_esperado
        and bool(anulaciones_ctx['movimientos_efectivo_rows'])
    )

    if usar_movimientos_efectivo_anulacion:
        for row in anulaciones_ctx['movimientos_efectivo_rows']:
            venta = ventas_anuladas.get(int(row['id_venta']))
            if not venta:
                continue
            metodo = metodos_por_id.get(int(efectivo_id))
            forma_pago = metodo.nombre if metodo else 'Efectivo'
            fecha_anulacion = anulacion_fecha_por_venta.get(int(venta.id_venta)) or row['fecha'] or venta.fecha_venta
            detalles.append(
                {
                    'fecha': fecha_anulacion,
                    'concepto': 'Anulación de Venta',
                    'referencia': f'Venta #{venta.id_venta}',
                    'forma_pago': forma_pago,
                    'entrada': 0.0,
                    'salida': _money(row['total']),
                    'detalle': resumenes_ventas.get(int(venta.id_venta), ''),
                    'tx_tipo': 'venta',
                    'tx_id': int(venta.id_venta),
                }
            )

    for r in anulaciones_pagos_rows:
        metodo_id = int(r.id_metodo_pago or 0)
        if usar_movimientos_efectivo_anulacion and efectivo_id is not None and metodo_id == int(efectivo_id):
            continue
        venta = ventas_anuladas.get(int(r.id_venta))
        if not venta:
            continue
        fecha_anulacion = anulacion_fecha_por_venta.get(int(venta.id_venta)) or venta.fecha_venta
        metodo = metodos_por_id.get(metodo_id)
        forma_pago = metodo.nombre if metodo else f'Método #{metodo_id}'
        detalles.append(
            {
                'fecha': fecha_anulacion,
                'concepto': 'Anulación de Venta',
                'referencia': f'Venta #{venta.id_venta}',
                'forma_pago': forma_pago,
                'entrada': 0.0,
                'salida': _money(r.total),
                'detalle': resumenes_ventas.get(int(venta.id_venta), ''),
                'tx_tipo': 'venta',
                'tx_id': int(venta.id_venta),
            }
        )

    pagos_creditos_detalle = (
        db.session.query(PagoCuentaCobrar, CuentaPorCobrar, MetodoPago)
        .join(CuentaPorCobrar, PagoCuentaCobrar.id_cuenta_cobrar == CuentaPorCobrar.id_cuenta_cobrar)
        .outerjoin(MetodoPago, PagoCuentaCobrar.id_metodo_pago == MetodoPago.id_metodo_pago)
        .filter(
            PagoCuentaCobrar.id_sesion_caja == id_sesion,
            PagoCuentaCobrar.estado != 'anulado',
        )
        .order_by(PagoCuentaCobrar.fecha_pago.asc(), PagoCuentaCobrar.id_pago_cuenta.asc())
        .all()
    )
    for pago, cuenta, metodo in pagos_creditos_detalle:
        ref = f'Cuenta #{cuenta.id_cuenta_cobrar}'
        if cuenta.id_venta:
            ref = f'Venta #{cuenta.id_venta} (Cuenta #{cuenta.id_cuenta_cobrar})'
        forma_pago = metodo.nombre if metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
        detalles.append(
            {
                'fecha': pago.fecha_pago,
                'concepto': 'Cobro de Crédito',
                'referencia': ref,
                'forma_pago': forma_pago,
                'entrada': _money(pago.monto),
                'salida': 0.0,
                'detalle': '',
                'tx_tipo': 'cobro_credito',
                'tx_id': int(pago.id_pago_cuenta),
                'tx_cuenta_id': int(cuenta.id_cuenta_cobrar),
                'tx_venta_id': int(cuenta.id_venta) if cuenta.id_venta else None,
            }
        )

    pagos_pedidos_detalle = (
        db.session.query(PedidoClientePago, PedidoCliente, MetodoPago)
        .join(PedidoCliente, PedidoClientePago.id_pedido == PedidoCliente.id_pedido)
        .outerjoin(MetodoPago, PedidoClientePago.id_metodo_pago == MetodoPago.id_metodo_pago)
        .filter(
            PedidoClientePago.id_sesion_caja == id_sesion,
            PedidoClientePago.estado == 'activo',
        )
        .order_by(PedidoClientePago.fecha_pago.asc(), PedidoClientePago.id_pago_pedido.asc())
        .all()
    )
    for pago, pedido, metodo in pagos_pedidos_detalle:
        forma_pago = metodo.nombre if metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
        detalles.append(
            {
                'fecha': pago.fecha_pago,
                'concepto': 'Cobro de Pedido',
                'referencia': pedido.numero_pedido_display,
                'forma_pago': forma_pago,
                'entrada': _money(pago.monto),
                'salida': 0.0,
                'detalle': pedido.cliente.nombre if pedido.cliente else '',
                'tx_tipo': 'pago_pedido',
                'tx_id': int(pago.id_pago_pedido),
                'tx_pedido_id': int(pedido.id_pedido),
            }
        )

    pagos_compras_detalle = (
        db.session.query(PagoCompra, Compra, MetodoPago)
        .join(Compra, PagoCompra.id_compra == Compra.id_compra)
        .outerjoin(MetodoPago, PagoCompra.id_metodo_pago == MetodoPago.id_metodo_pago)
        .filter(PagoCompra.id_sesion_caja == id_sesion)
        .order_by(PagoCompra.fecha_pago.asc(), PagoCompra.id_pago_compra.asc())
        .all()
    )
    resumenes_compras = _resumenes_compras_por_ids(int(compra.id_compra) for _, compra, _ in pagos_compras_detalle)
    for pago, compra, metodo in pagos_compras_detalle:
        descripcion = resumenes_compras.get(int(compra.id_compra), '')
        forma_pago = metodo.nombre if metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
        detalles.append(
            {
                'fecha': pago.fecha_pago,
                'concepto': 'Pago de Compra',
                'referencia': f'Compra #{pago.id_compra}',
                'forma_pago': forma_pago,
                'entrada': 0.0,
                'salida': _money(pago.monto),
                'detalle': descripcion,
                'tx_tipo': 'pago_compra',
                'tx_id': int(pago.id_pago_compra),
                'tx_compra_id': int(pago.id_compra),
            }
        )

    for mov in movimientos:
        referencia_tipo = (mov.referencia_tipo or '').strip().lower()
        if referencia_tipo == 'compra':
            continue
        if mov.tipo == 'egreso' and referencia_tipo == 'anulacion_venta':
            continue
        if mov.tipo == 'ingreso' and referencia_tipo == 'venta':
            continue
        if mov.tipo == 'ingreso' and referencia_tipo == 'pago_pedido':
            continue

        detalles.append(
            {
                'fecha': mov.fecha_movimiento,
                'concepto': 'Movimiento de Caja',
                'referencia': getattr(mov, 'motivo_detallado', None) or mov.motivo,
                'forma_pago': 'Efectivo',
                'entrada': _money(mov.monto) if mov.tipo == 'ingreso' else 0.0,
                'salida': _money(mov.monto) if mov.tipo == 'egreso' else 0.0,
                'detalle': '',
                'tx_tipo': 'movimiento_caja',
                'tx_id': int(mov.id_movimiento_caja),
            }
        )

    detalles.sort(key=lambda x: (x['fecha'] or datetime.min, x['concepto'], x['referencia']))

    from app.routes.caja.alertas_cuadre import calcular_alertas_cuadre_sesion

    alertas_cuadre = calcular_alertas_cuadre_sesion(
        sesion=sesion,
        efectivo_id=efectivo_id,
        pagos_ventas_agg=pagos_ventas_agg,
        movimientos=movimientos,
        anulaciones_efectivo_esperado=anulaciones_efectivo_esperado,
        anulaciones_efectivo_mov=anulaciones_efectivo_mov,
    )

    return {
        'sesion': sesion,
        'ventas_por_metodo': ventas_por_metodo,
        'creditos_por_metodo': creditos_por_metodo,
        'pedidos_por_metodo': pedidos_por_metodo,
        'compras_por_metodo': compras_por_metodo,
        'movimientos': movimientos,
        'conceptos': conceptos,
        'detalles': detalles,
        'total_ingresos': total_ingresos,
        'total_egresos': total_egresos,
        'neto': neto,
        'total_efectivo_sistema': total_efectivo_sistema,
        'ingreso_real_efectivo': ingreso_real_efectivo,
        'declarado': declarado,
        'diferencia_efectivo': diferencia_efectivo,
        'efectivo_id': efectivo_id,
        'alertas_cuadre': alertas_cuadre,
    }


def _calcular_informe_contable_rango(start_utc: datetime, end_utc: datetime):
    from app.routes.caja.contabilidad_report import calcular_informe_contable_rango

    return calcular_informe_contable_rango(start_utc, end_utc)
