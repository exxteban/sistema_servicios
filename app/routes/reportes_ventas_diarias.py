from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    DetalleVenta,
    PagoCuentaCobrar,
    PagoVenta,
    PedidoCliente,
    PedidoClientePago,
    Producto,
    SesionCaja,
    Venta,
)
from app.utils.helpers import parse_iso_date, today_local, utc_bounds_for_local_dates


def _resolver_fechas_ventas_diarias(raw_desde, raw_hasta, raw_fecha):
    if raw_desde or raw_hasta:
        desde = parse_iso_date(raw_desde) or parse_iso_date(raw_hasta) or today_local()
        hasta = parse_iso_date(raw_hasta) or desde
    else:
        fecha = raw_fecha or today_local().isoformat()
        desde = parse_iso_date(fecha) or today_local()
        hasta = desde

    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde

    return desde, hasta


def _nombre_vendedor_venta(venta):
    if getattr(venta, 'vendedor', None):
        return venta.vendedor.nombre_completo
    if getattr(venta, 'sesion_caja', None) and getattr(venta.sesion_caja, 'usuario', None):
        return venta.sesion_caja.usuario.nombre_completo
    return 'Desconocido'


def _armar_detalles_por_venta(ventas):
    detalles_por_venta = {}
    venta_ids = [int(venta.id_venta) for venta in ventas]
    if not venta_ids:
        return detalles_por_venta

    for venta in ventas:
        detalle = ''
        reparacion = getattr(venta, 'reparacion', None)
        if reparacion is not None:
            detalle = (reparacion.solucion or reparacion.diagnostico_tecnico or reparacion.falla_reportada or '').strip()
            detalle = f"Reparación: {detalle}" if detalle else "Reparación"
        detalles_por_venta[int(venta.id_venta)] = detalle

    rows = (
        db.session.query(
            DetalleVenta.id_venta,
            Producto.nombre,
            db.func.sum(DetalleVenta.cantidad).label('cantidad'),
        )
        .join(Producto, Producto.id_producto == DetalleVenta.id_producto)
        .filter(DetalleVenta.id_venta.in_(venta_ids))
        .group_by(DetalleVenta.id_venta, Producto.nombre)
        .order_by(DetalleVenta.id_venta.asc(), Producto.nombre.asc())
        .all()
    )

    agrupado = {}
    for id_venta, nombre, cantidad in rows:
        agrupado.setdefault(int(id_venta), []).append((nombre, int(cantidad or 0)))

    for venta in ventas:
        venta_id = int(venta.id_venta)
        if detalles_por_venta.get(venta_id):
            continue
        partes = []
        for nombre, cantidad in agrupado.get(venta_id, []):
            partes.append(f"{nombre} x{cantidad}" if cantidad and cantidad != 1 else nombre)
        detalles_por_venta[venta_id] = ", ".join([parte for parte in partes if parte]) or (venta.observaciones or '').strip()

    return detalles_por_venta


def _numero_pedido_display(id_pedido, numero_pedido):
    numero = int(numero_pedido or id_pedido or 0)
    return f'PED-{numero:06d}' if numero > 0 else 'PED-PENDIENTE'


def _armar_desglose_cobros_pedidos(start_utc, end_utc):
    rows = (
        db.session.query(
            PedidoClientePago.id_pedido,
            PedidoCliente.numero_pedido,
            PedidoCliente.id_venta_generada,
            func.count(PedidoClientePago.id_pago_pedido).label('cantidad_pagos'),
            func.sum(PedidoClientePago.monto).label('total_cobrado'),
            func.max(PedidoClientePago.fecha_pago).label('ultimo_pago'),
        )
        .join(PedidoCliente, PedidoCliente.id_pedido == PedidoClientePago.id_pedido)
        .filter(
            PedidoClientePago.fecha_pago >= start_utc,
            PedidoClientePago.fecha_pago < end_utc,
            PedidoClientePago.estado == 'activo',
        )
        .group_by(
            PedidoClientePago.id_pedido,
            PedidoCliente.numero_pedido,
            PedidoCliente.id_venta_generada,
        )
        .order_by(func.sum(PedidoClientePago.monto).desc(), func.max(PedidoClientePago.fecha_pago).desc())
        .all()
    )

    return [
        {
            'id_pedido': int(id_pedido),
            'numero_pedido': _numero_pedido_display(id_pedido, numero_pedido),
            'id_venta_generada': int(id_venta_generada) if id_venta_generada else None,
            'cantidad_pagos': int(cantidad_pagos or 0),
            'total_cobrado': float(total_cobrado or 0),
            'ultimo_pago': ultimo_pago,
        }
        for id_pedido, numero_pedido, id_venta_generada, cantidad_pagos, total_cobrado, ultimo_pago in rows
    ]


def construir_contexto_ventas_diarias(*, raw_desde=None, raw_hasta=None, raw_fecha=None):
    desde, hasta = _resolver_fechas_ventas_diarias(raw_desde, raw_hasta, raw_fecha)
    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)
    periodo_label = 'dia' if desde == hasta else 'periodo'

    ventas = (
        Venta.query.options(
            joinedload(Venta.cliente),
            joinedload(Venta.cuenta_por_cobrar),
            joinedload(Venta.sesion_caja).joinedload(SesionCaja.usuario),
            joinedload(Venta.vendedor),
            joinedload(Venta.reparacion),
        )
        .filter(
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
            Venta.estado == 'completada',
        )
        .order_by(Venta.fecha_venta)
        .all()
    )

    total_emitido = sum(float(venta.total or 0) for venta in ventas)
    vendedor_por_venta = {int(venta.id_venta): _nombre_vendedor_venta(venta) for venta in ventas}
    detalles_por_venta = _armar_detalles_por_venta(ventas)

    venta_ids = [int(venta.id_venta) for venta in ventas]
    pagos_por_venta = {}
    if venta_ids:
        pagos_rows = (
            db.session.query(
                PagoVenta.id_venta,
                func.sum(PagoVenta.monto).label('monto_pagado'),
            )
            .filter(PagoVenta.id_venta.in_(venta_ids))
            .group_by(PagoVenta.id_venta)
            .all()
        )
        pagos_por_venta = {
            int(id_venta): float(monto_pagado or 0)
            for id_venta, monto_pagado in pagos_rows
        }

    total_cobrado_al_momento = sum(pagos_por_venta.get(int(venta.id_venta), 0.0) for venta in ventas)
    ventas_credito = [
        venta for venta in ventas
        if (venta.tipo_venta or 'contado').strip().lower() == 'credito'
    ]
    total_credito_generado = sum(
        float(
            getattr(getattr(venta, 'cuenta_por_cobrar', None), 'monto_total', venta.saldo_pendiente) or 0
        )
        for venta in ventas_credito
    )
    total_cobros_ventas_dia = (
        db.session.query(func.sum(PagoVenta.monto))
        .join(Venta, PagoVenta.id_venta == Venta.id_venta)
        .filter(
            PagoVenta.fecha_pago >= start_utc,
            PagoVenta.fecha_pago < end_utc,
            Venta.estado == 'completada',
        )
        .scalar()
    )
    total_cobros_ventas_dia = float(total_cobros_ventas_dia or 0)
    total_cobros_credito_dia = (
        db.session.query(func.sum(PagoCuentaCobrar.monto))
        .filter(
            PagoCuentaCobrar.fecha_pago >= start_utc,
            PagoCuentaCobrar.fecha_pago < end_utc,
            PagoCuentaCobrar.estado != 'anulado',
        )
        .scalar()
    )
    total_cobros_credito_dia = float(total_cobros_credito_dia or 0)
    cobros_pedidos_dia = (
        db.session.query(func.sum(PedidoClientePago.monto))
        .filter(
            PedidoClientePago.fecha_pago >= start_utc,
            PedidoClientePago.fecha_pago < end_utc,
            PedidoClientePago.estado == 'activo',
        )
        .scalar()
    )
    cobros_pedidos_dia = float(cobros_pedidos_dia or 0)
    desglose_cobros_pedidos = _armar_desglose_cobros_pedidos(start_utc, end_utc)
    recaudacion_total_dia = total_cobros_ventas_dia + total_cobros_credito_dia + cobros_pedidos_dia

    return {
        'ventas': ventas,
        'vendedor_por_venta': vendedor_por_venta,
        'detalles_por_venta': detalles_por_venta,
        'desde': desde,
        'hasta': hasta,
        'total': total_emitido,
        'total_emitido': total_emitido,
        'total_cobrado_al_momento': total_cobrado_al_momento,
        'total_cobros_ventas_dia': total_cobros_ventas_dia,
        'total_cobros_credito_dia': total_cobros_credito_dia,
        'cobros_pedidos_dia': cobros_pedidos_dia,
        'desglose_cobros_pedidos': desglose_cobros_pedidos,
        'recaudacion_total_dia': recaudacion_total_dia,
        'ventas_cerradas_dia': total_emitido,
        'ventas_credito_count': len(ventas_credito),
        'total_credito_generado': total_credito_generado,
        'periodo_label': periodo_label,
        'show_date_in_labels': (desde != hasta),
    }
