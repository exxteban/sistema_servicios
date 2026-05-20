from __future__ import annotations

from sqlalchemy.orm import joinedload

from app.models import DetalleCompra, DetalleDevolucion, DetalleVenta, Venta


def _resumen_productos(detalles):
    try:
        items = list(detalles)
    except Exception:
        return ''
    if not items:
        return ''

    partes = []
    restantes = 0
    for index, det in enumerate(items):
        producto = getattr(det, 'producto', None)
        nombre = getattr(producto, 'nombre', '') if producto else ''
        if not nombre:
            nombre = 'Producto'
        cantidad = getattr(det, 'cantidad', None)
        if index < 3:
            partes.append(f'{cantidad} x {nombre}' if cantidad is not None else nombre)
        else:
            restantes += 1
    if restantes:
        partes.append(f'+ {restantes} más')
    return ', '.join(partes)


def _enriquecer_motivos_movimientos(movimientos):
    if not movimientos:
        return movimientos

    venta_ids = set()
    compra_ids = set()
    devolucion_ids = set()
    pago_gasto_ids = set()

    for mov in movimientos:
        rid = getattr(mov, 'referencia_id', None)
        if not rid:
            continue
        referencia_tipo = (getattr(mov, 'referencia_tipo', '') or '').strip().lower()
        try:
            rid_int = int(rid)
        except Exception:
            continue
        if referencia_tipo in {'venta', 'anulacion_venta'}:
            venta_ids.add(rid_int)
        elif referencia_tipo == 'compra':
            compra_ids.add(rid_int)
        elif referencia_tipo == 'devolucion':
            devolucion_ids.add(rid_int)
        elif referencia_tipo in {'gasto_corriente', 'gasto_corriente_reversa'}:
            pago_gasto_ids.add(rid_int)

    detalles_ventas_por_id = {}
    if venta_ids:
        rows = (
            DetalleVenta.query.options(joinedload(DetalleVenta.producto))
            .filter(DetalleVenta.id_venta.in_(sorted(venta_ids)))
            .order_by(DetalleVenta.id_venta.asc(), DetalleVenta.id_detalle_venta.asc())
            .all()
        )
        for detalle in rows:
            detalles_ventas_por_id.setdefault(int(detalle.id_venta), []).append(detalle)

    detalles_compras_por_id = {}
    if compra_ids:
        rows = (
            DetalleCompra.query.options(joinedload(DetalleCompra.producto))
            .filter(DetalleCompra.id_compra.in_(sorted(compra_ids)))
            .order_by(DetalleCompra.id_compra.asc(), DetalleCompra.id_detalle_compra.asc())
            .all()
        )
        for detalle in rows:
            detalles_compras_por_id.setdefault(int(detalle.id_compra), []).append(detalle)

    detalles_devoluciones_por_id = {}
    if devolucion_ids:
        rows = (
            DetalleDevolucion.query.options(joinedload(DetalleDevolucion.producto))
            .filter(DetalleDevolucion.id_devolucion.in_(sorted(devolucion_ids)))
            .order_by(DetalleDevolucion.id_devolucion.asc(), DetalleDevolucion.id_detalle_devolucion.asc())
            .all()
        )
        for detalle in rows:
            detalles_devoluciones_por_id.setdefault(int(detalle.id_devolucion), []).append(detalle)

    pagos_gastos_por_id = {}
    if pago_gasto_ids:
        from gastos_corrientes.models import PagoGastoCorriente

        rows = (
            PagoGastoCorriente.query.options(joinedload(PagoGastoCorriente.gasto_corriente))
            .filter(PagoGastoCorriente.id_pago_gasto_corriente.in_(sorted(pago_gasto_ids)))
            .all()
        )
        for pago in rows:
            pagos_gastos_por_id[int(pago.id_pago_gasto_corriente)] = pago

    resumen_ventas = {key: _resumen_productos(value) for key, value in detalles_ventas_por_id.items()}
    resumen_compras = {key: _resumen_productos(value) for key, value in detalles_compras_por_id.items()}
    resumen_devoluciones = {key: _resumen_productos(value) for key, value in detalles_devoluciones_por_id.items()}
    estados_ventas = {}
    if venta_ids:
        rows = (
            Venta.query.with_entities(Venta.id_venta, Venta.estado)
            .filter(Venta.id_venta.in_(sorted(venta_ids)))
            .all()
        )
        for row in rows:
            try:
                estados_ventas[int(row[0])] = (row[1] or '').strip().lower()
            except Exception:
                continue

    for mov in movimientos:
        base = (getattr(mov, 'motivo', '') or '').strip()
        rid = getattr(mov, 'referencia_id', None)
        referencia_tipo = (getattr(mov, 'referencia_tipo', '') or '').strip().lower()

        try:
            rid_int = int(rid) if rid else None
        except Exception:
            rid_int = None

        resumen = ''
        if referencia_tipo in {'venta', 'anulacion_venta'} and rid_int:
            resumen = (resumen_ventas.get(rid_int) or '').strip()
        elif referencia_tipo == 'compra' and rid_int:
            resumen = (resumen_compras.get(rid_int) or '').strip()
        elif referencia_tipo == 'devolucion' and rid_int:
            resumen = (resumen_devoluciones.get(rid_int) or '').strip()
        elif referencia_tipo in {'gasto_corriente', 'gasto_corriente_reversa'} and rid_int:
            pago_gasto = pagos_gastos_por_id.get(rid_int)
            gasto = getattr(pago_gasto, 'gasto_corriente', None) if pago_gasto else None
            nombre = (getattr(gasto, 'nombre', '') or '').strip()
            categoria = (getattr(gasto, 'categoria', '') or '').replace('_', ' ').title().strip()
            periodo = (getattr(pago_gasto, 'periodo', '') or '').strip() if pago_gasto else ''
            partes = []
            if nombre:
                partes.append(nombre)
            if categoria:
                partes.append(f'Categoría: {categoria}')
            if periodo:
                partes.append(f'Período: {periodo}')
            resumen = ' · '.join(partes)

        motivo_detallado = base
        estado_venta = estados_ventas.get(rid_int) if rid_int else None
        if estado_venta == 'anulada' and '(ANULADA)' not in motivo_detallado:
            motivo_detallado = f'{motivo_detallado} (ANULADA)'.strip()
        if resumen and resumen not in motivo_detallado:
            motivo_detallado = f'{motivo_detallado}: {resumen}' if motivo_detallado else resumen
        setattr(mov, 'motivo_detallado', motivo_detallado)

    return movimientos


def _descripcion_venta_detalle(venta):
    if not venta:
        return ''
    return _resumen_productos(venta.detalles)


def _descripcion_compra_detalle(compra):
    if not compra:
        return ''
    return _resumen_productos(compra.detalles)


def _resumenes_ventas_por_ids(venta_ids):
    ids = sorted({int(venta_id) for venta_id in venta_ids if venta_id})
    if not ids:
        return {}

    rows = (
        DetalleVenta.query.options(joinedload(DetalleVenta.producto))
        .filter(DetalleVenta.id_venta.in_(ids))
        .order_by(DetalleVenta.id_venta.asc(), DetalleVenta.id_detalle_venta.asc())
        .all()
    )

    detalles_por_id = {}
    for detalle in rows:
        detalles_por_id.setdefault(int(detalle.id_venta), []).append(detalle)

    return {venta_id: _resumen_productos(detalles) for venta_id, detalles in detalles_por_id.items()}


def _resumenes_compras_por_ids(compra_ids):
    ids = sorted({int(compra_id) for compra_id in compra_ids if compra_id})
    if not ids:
        return {}

    rows = (
        DetalleCompra.query.options(joinedload(DetalleCompra.producto))
        .filter(DetalleCompra.id_compra.in_(ids))
        .order_by(DetalleCompra.id_compra.asc(), DetalleCompra.id_detalle_compra.asc())
        .all()
    )

    detalles_por_id = {}
    for detalle in rows:
        detalles_por_id.setdefault(int(detalle.id_compra), []).append(detalle)

    return {compra_id: _resumen_productos(detalles) for compra_id, detalles in detalles_por_id.items()}
