from datetime import datetime

from flask import current_app, flash, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    Auditoria,
    Compra,
    CuentaPorCobrar,
    DetalleCompra,
    DetalleVenta,
    MetodoPago,
    MovimientoCaja,
    PedidoCliente,
    PedidoClientePago,
    PagoCompra,
    PagoCuentaCobrar,
    PagoVenta,
    SesionCaja,
    Venta,
)
from app.routes.caja import caja_bp
from app.routes.caja.common import (
    _calcular_informe_cierre_sesion,
    _descripcion_compra_detalle,
    _descripcion_venta_detalle,
    _enriquecer_motivos_movimientos,
    _puede_ver_sesion,
    _resolver_metodo_efectivo_id,
)
from app.services.caja_cuadre import obtener_resumen_anulaciones_ventas_sesion
from app.utils.auditoria_utils import registrar_auditoria
from app.utils.helpers import local_strftime, parse_iso_date, today_local, utc_bounds_for_local_dates


@caja_bp.route('/cierres/<int:id_sesion>/transacciones/detalle')
@login_required
def cierre_transaccion_detalle(id_sesion):
    if not current_user.tiene_permiso('ver_caja'):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

    sesion = (
        SesionCaja.query.options(
            joinedload(SesionCaja.caja),
            joinedload(SesionCaja.usuario),
            joinedload(SesionCaja.usuario_cierre),
        )
        .get_or_404(id_sesion)
    )
    if not _puede_ver_sesion(sesion):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

    tipo = (request.args.get('tipo') or '').strip().lower()
    ref_id = request.args.get('id', type=int)
    if not tipo or not ref_id:
        return jsonify({'error': 'Solicitud inválida'}), 400

    if tipo == 'sesion_apertura':
        return jsonify(
            {
                'tipo': 'sesion_apertura',
                'id': int(sesion.id_sesion),
                'caja': sesion.caja.nombre if sesion.caja else '',
                'usuario_apertura': sesion.usuario.nombre_completo if sesion.usuario else '',
                'usuario_cierre': sesion.usuario_cierre.nombre_completo if sesion.usuario_cierre else '',
                'fecha_apertura': local_strftime(sesion.fecha_apertura, '%d/%m/%Y %H:%M'),
                'fecha_cierre': local_strftime(sesion.fecha_cierre, '%d/%m/%Y %H:%M'),
                'monto_inicial': float(sesion.monto_inicial or 0),
            }
        )

    if tipo == 'venta':
        venta = (
            Venta.query.options(
                joinedload(Venta.cliente),
                joinedload(Venta.sesion_caja).joinedload(SesionCaja.usuario),
                joinedload(Venta.vendedor),
            )
            .get_or_404(ref_id)
        )
        if int(venta.id_sesion_caja) != int(id_sesion):
            return jsonify({'error': 'No encontrado'}), 404

        detalles = (
            DetalleVenta.query.options(joinedload(DetalleVenta.producto), joinedload(DetalleVenta.servicio))
            .filter(DetalleVenta.id_venta == venta.id_venta)
            .all()
        )
        items = [
            {
                'producto': d.item_nombre,
                'cantidad': int(d.cantidad or 0),
                'precio_unitario': float(d.precio_unitario or 0),
                'subtotal': float(d.subtotal or 0),
                'descuento': float(getattr(d, 'descuento_linea', 0) or 0),
            }
            for d in detalles
        ]

        pagos = (
            PagoVenta.query.options(joinedload(PagoVenta.metodo))
            .filter(PagoVenta.id_venta == venta.id_venta)
            .order_by(PagoVenta.id_pago.asc())
            .all()
        )
        pagos_json = [
            {
                'metodo': p.metodo.nombre if p.metodo else '',
                'monto': float(p.monto or 0),
            }
            for p in pagos
        ]

        vendedor = None
        if getattr(venta, 'vendedor', None):
            vendedor = venta.vendedor.nombre_completo
        elif getattr(venta, 'sesion_caja', None) and getattr(venta.sesion_caja, 'usuario', None):
            vendedor = venta.sesion_caja.usuario.nombre_completo

        return jsonify(
            {
                'tipo': 'venta',
                'id': int(venta.id_venta),
                'fecha': local_strftime(venta.fecha_venta, '%d/%m/%Y %H:%M'),
                'cliente': venta.cliente.nombre if venta.cliente else '',
                'vendedor': vendedor,
                'items': items,
                'total': float(venta.total or 0),
                'pagos': pagos_json,
                'urls': {
                    'detalle': url_for('ventas.detalle', id=int(venta.id_venta)),
                    'ticket': url_for('ventas.ticket', id=int(venta.id_venta)),
                },
            }
        )

    if tipo == 'pago_compra':
        pago = (
            PagoCompra.query.options(
                joinedload(PagoCompra.metodo),
                joinedload(PagoCompra.usuario),
            )
            .get_or_404(ref_id)
        )
        if int(pago.id_sesion_caja or 0) != int(id_sesion):
            return jsonify({'error': 'No encontrado'}), 404

        compra = (
            Compra.query.options(
                joinedload(Compra.proveedor),
                joinedload(Compra.usuario),
            )
            .get_or_404(int(pago.id_compra))
        )

        detalles = (
            DetalleCompra.query.options(joinedload(DetalleCompra.producto))
            .filter(DetalleCompra.id_compra == compra.id_compra)
            .all()
        )
        items = [
            {
                'producto': d.producto.nombre if d.producto else '',
                'cantidad': int(d.cantidad or 0),
                'subtotal': float(d.subtotal or 0),
            }
            for d in detalles
        ]

        pagos_compra = (
            PagoCompra.query.options(joinedload(PagoCompra.metodo))
            .filter(PagoCompra.id_compra == compra.id_compra)
            .order_by(PagoCompra.fecha_pago.asc(), PagoCompra.id_pago_compra.asc())
            .all()
        )
        pagos_json = [
            {
                'metodo': p.metodo.nombre if p.metodo else '',
                'monto': float(p.monto or 0),
            }
            for p in pagos_compra
        ]

        return jsonify(
            {
                'tipo': 'pago_compra',
                'id': int(pago.id_pago_compra),
                'fecha': local_strftime(pago.fecha_pago, '%d/%m/%Y %H:%M'),
                'monto': float(pago.monto or 0),
                'metodo': pago.metodo.nombre if pago.metodo else '',
                'usuario': pago.usuario.nombre_completo if pago.usuario else '',
                'compra': {
                    'id': int(compra.id_compra),
                    'fecha': compra.fecha_compra.strftime('%d/%m/%Y') if compra.fecha_compra else '',
                    'proveedor': compra.proveedor.nombre if compra.proveedor else '',
                    'factura': compra.numero_factura or '',
                    'total': float(compra.total or 0),
                    'items': items,
                    'pagos': pagos_json,
                },
                'urls': {
                    'compra': url_for('compras.detalle', id=int(compra.id_compra)),
                },
            }
        )

    if tipo == 'cobro_credito':
        pago = (
            PagoCuentaCobrar.query.options(
                joinedload(PagoCuentaCobrar.metodo),
                joinedload(PagoCuentaCobrar.usuario),
            )
            .get_or_404(ref_id)
        )
        if int(pago.id_sesion_caja or 0) != int(id_sesion):
            return jsonify({'error': 'No encontrado'}), 404

        cuenta = (
            CuentaPorCobrar.query.options(joinedload(CuentaPorCobrar.cliente)).get_or_404(int(pago.id_cuenta_cobrar))
        )

        venta_url = url_for('ventas.detalle', id=int(cuenta.id_venta)) if cuenta.id_venta else None

        return jsonify(
            {
                'tipo': 'cobro_credito',
                'id': int(pago.id_pago_cuenta),
                'fecha': local_strftime(pago.fecha_pago, '%d/%m/%Y %H:%M'),
                'monto': float(pago.monto or 0),
                'estado': pago.estado,
                'metodo': pago.metodo.nombre if pago.metodo else '',
                'usuario': pago.usuario.nombre_completo if pago.usuario else '',
                'cuenta': {
                    'id': int(cuenta.id_cuenta_cobrar),
                    'cliente': cuenta.cliente.nombre if cuenta.cliente else '',
                    'monto_total': float(cuenta.monto_total or 0),
                    'monto_cobrado': float(cuenta.monto_cobrado or 0),
                    'saldo_pendiente': float(cuenta.saldo_pendiente or 0),
                    'venta_id': int(cuenta.id_venta) if cuenta.id_venta else None,
                },
                'urls': {
                    'venta': venta_url,
                },
            }
        )

    if tipo == 'pago_pedido':
        pago = (
            PedidoClientePago.query.options(
                joinedload(PedidoClientePago.metodo),
                joinedload(PedidoClientePago.usuario),
                joinedload(PedidoClientePago.pedido).joinedload(PedidoCliente.cliente),
            )
            .get_or_404(ref_id)
        )
        if int(pago.id_sesion_caja or 0) != int(id_sesion):
            return jsonify({'error': 'No encontrado'}), 404

        pedido = pago.pedido
        return jsonify(
            {
                'tipo': 'pago_pedido',
                'id': int(pago.id_pago_pedido),
                'fecha': local_strftime(pago.fecha_pago, '%d/%m/%Y %H:%M'),
                'monto': float(pago.monto or 0),
                'estado': pago.estado,
                'metodo': pago.metodo.nombre if pago.metodo else '',
                'usuario': pago.usuario.nombre_completo if pago.usuario else '',
                'pedido': {
                    'id': int(pedido.id_pedido) if pedido else None,
                    'numero': pedido.numero_pedido_display if pedido else '',
                    'cliente': pedido.cliente.nombre if pedido and pedido.cliente else '',
                    'estado': pedido.estado if pedido else '',
                    'total': float(pedido.total or 0) if pedido else 0,
                    'total_pagado': float(pedido.total_pagado or 0) if pedido else 0,
                    'saldo_pendiente': float(pedido.saldo_pendiente or 0) if pedido else 0,
                },
                'tipo_pago': pago.tipo_pago,
                'referencia': pago.referencia or '',
                'urls': {
                    'pedido': url_for('pedidos.detalle', id_pedido=int(pedido.id_pedido)) if pedido else None,
                },
            }
        )

    if tipo == 'movimiento_caja':
        mov = MovimientoCaja.query.options(joinedload(MovimientoCaja.usuario)).get_or_404(ref_id)
        if int(mov.id_sesion_caja) != int(id_sesion):
            return jsonify({'error': 'No encontrado'}), 404
        _enriquecer_motivos_movimientos([mov])

        return jsonify(
            {
                'tipo': 'movimiento_caja',
                'id': int(mov.id_movimiento_caja),
                'fecha': local_strftime(mov.fecha_movimiento, '%d/%m/%Y %H:%M'),
                'movimiento_tipo': mov.tipo,
                'monto': float(mov.monto or 0),
                'motivo': getattr(mov, 'motivo_detallado', None) or mov.motivo or '',
                'usuario': mov.usuario.nombre_completo if mov.usuario else '',
                'referencia_tipo': (mov.referencia_tipo or '').strip(),
                'referencia_id': int(mov.referencia_id) if mov.referencia_id else None,
            }
        )

    return jsonify({'error': 'Tipo no soportado'}), 400


@caja_bp.route('/cierres/<int:id_sesion>/conceptos/transacciones')
@login_required
def cierre_concepto_transacciones(id_sesion):
    if not current_user.tiene_permiso('ver_caja'):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

    sesion = (
        SesionCaja.query.options(
            joinedload(SesionCaja.caja),
            joinedload(SesionCaja.usuario),
            joinedload(SesionCaja.usuario_cierre),
        )
        .get_or_404(id_sesion)
    )
    if not _puede_ver_sesion(sesion):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

    key = (request.args.get('key') or '').strip().lower()
    metodo_id = request.args.get('metodo_id', type=int)
    if not key:
        return jsonify({'error': 'Solicitud inválida'}), 400

    def _money(x):
        try:
            return float(x or 0)
        except Exception:
            return 0.0

    items = []

    if key == 'caja_inicial':
        if sesion.fecha_apertura:
            items.append(
                {
                    'fecha': local_strftime(sesion.fecha_apertura, '%d/%m/%Y %H:%M'),
                    'concepto': 'Caja Inicial',
                    'referencia': f'Sesión #{sesion.id_sesion}',
                    'detalle': '',
                    'forma_pago': 'Efectivo',
                    'entrada': _money(sesion.monto_inicial),
                    'salida': 0.0,
                    'tx_tipo': 'sesion_apertura',
                    'tx_id': int(sesion.id_sesion),
                }
            )

    elif key in {'ventas_metodo', 'ventas_efectivo_mov'}:
        if key == 'ventas_metodo' and not metodo_id:
            return jsonify({'error': 'Solicitud inválida'}), 400

        if key == 'ventas_metodo':
            pagos = (
                db.session.query(PagoVenta, Venta, MetodoPago)
                .join(Venta, PagoVenta.id_venta == Venta.id_venta)
                .outerjoin(MetodoPago, PagoVenta.id_metodo_pago == MetodoPago.id_metodo_pago)
                .options(joinedload(Venta.cliente))
                .filter(
                    Venta.id_sesion_caja == id_sesion,
                    Venta.estado == 'completada',
                    PagoVenta.id_metodo_pago == metodo_id,
                )
                .order_by(Venta.fecha_venta.asc(), PagoVenta.id_pago.asc())
                .all()
            )
            for pago, venta, metodo in pagos:
                forma_pago = metodo.nombre if metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
                items.append(
                    {
                        'fecha': local_strftime(venta.fecha_venta, '%d/%m/%Y %H:%M'),
                        'concepto': 'Venta',
                        'referencia': f'Venta #{venta.id_venta}',
                        'detalle': _descripcion_venta_detalle(venta),
                        'forma_pago': forma_pago,
                        'entrada': _money(pago.monto),
                        'salida': 0.0,
                        'tx_tipo': 'venta',
                        'tx_id': int(venta.id_venta),
                    }
                )
        else:
            movimientos = (
                MovimientoCaja.query.options(joinedload(MovimientoCaja.usuario))
                .filter(
                    MovimientoCaja.id_sesion_caja == id_sesion,
                    MovimientoCaja.tipo == 'ingreso',
                )
                .order_by(MovimientoCaja.fecha_movimiento.asc(), MovimientoCaja.id_movimiento_caja.asc())
                .all()
            )
            _enriquecer_motivos_movimientos(movimientos)
            for mov in movimientos:
                referencia_tipo = (mov.referencia_tipo or '').strip().lower()
                if referencia_tipo != 'venta':
                    continue
                items.append(
                    {
                        'fecha': local_strftime(mov.fecha_movimiento, '%d/%m/%Y %H:%M'),
                        'concepto': 'Movimiento de Caja',
                        'referencia': getattr(mov, 'motivo_detallado', None) or mov.motivo,
                        'detalle': '',
                        'forma_pago': 'Efectivo',
                        'entrada': _money(mov.monto),
                        'salida': 0.0,
                        'tx_tipo': 'movimiento_caja',
                        'tx_id': int(mov.id_movimiento_caja),
                    }
                )

    elif key == 'cobros_creditos_metodo':
        if not metodo_id:
            return jsonify({'error': 'Solicitud inválida'}), 400

        pagos = (
            db.session.query(PagoCuentaCobrar, CuentaPorCobrar, MetodoPago)
            .join(CuentaPorCobrar, PagoCuentaCobrar.id_cuenta_cobrar == CuentaPorCobrar.id_cuenta_cobrar)
            .outerjoin(MetodoPago, PagoCuentaCobrar.id_metodo_pago == MetodoPago.id_metodo_pago)
            .filter(
                PagoCuentaCobrar.id_sesion_caja == id_sesion,
                PagoCuentaCobrar.id_metodo_pago == metodo_id,
                PagoCuentaCobrar.estado != 'anulado',
            )
            .order_by(PagoCuentaCobrar.fecha_pago.asc(), PagoCuentaCobrar.id_pago_cuenta.asc())
            .all()
        )
        for pago, cuenta, metodo in pagos:
            ref = f'Cuenta #{cuenta.id_cuenta_cobrar}'
            if cuenta.id_venta:
                ref = f'Venta #{cuenta.id_venta} (Cuenta #{cuenta.id_cuenta_cobrar})'
            forma_pago = metodo.nombre if metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
            items.append(
                {
                    'fecha': local_strftime(pago.fecha_pago, '%d/%m/%Y %H:%M'),
                    'concepto': 'Cobro de Crédito',
                    'referencia': ref,
                    'detalle': '',
                    'forma_pago': forma_pago,
                    'entrada': _money(pago.monto),
                    'salida': 0.0,
                    'tx_tipo': 'cobro_credito',
                    'tx_id': int(pago.id_pago_cuenta),
                }
            )

    elif key == 'cobros_pedidos_metodo':
        if not metodo_id:
            return jsonify({'error': 'Solicitud inválida'}), 400

        pagos = (
            db.session.query(PedidoClientePago, PedidoCliente, MetodoPago)
            .join(PedidoCliente, PedidoClientePago.id_pedido == PedidoCliente.id_pedido)
            .outerjoin(MetodoPago, PedidoClientePago.id_metodo_pago == MetodoPago.id_metodo_pago)
            .options(joinedload(PedidoCliente.cliente))
            .filter(
                PedidoClientePago.id_sesion_caja == id_sesion,
                PedidoClientePago.id_metodo_pago == metodo_id,
                PedidoClientePago.estado == 'activo',
            )
            .order_by(PedidoClientePago.fecha_pago.asc(), PedidoClientePago.id_pago_pedido.asc())
            .all()
        )
        for pago, pedido, metodo in pagos:
            forma_pago = metodo.nombre if metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
            items.append(
                {
                    'fecha': local_strftime(pago.fecha_pago, '%d/%m/%Y %H:%M'),
                    'concepto': 'Cobro de Pedido',
                    'referencia': pedido.numero_pedido_display,
                    'detalle': pedido.cliente.nombre if pedido.cliente else '',
                    'forma_pago': forma_pago,
                    'entrada': _money(pago.monto),
                    'salida': 0.0,
                    'tx_tipo': 'pago_pedido',
                    'tx_id': int(pago.id_pago_pedido),
                }
            )

    elif key == 'pagos_compras_metodo':
        if not metodo_id:
            return jsonify({'error': 'Solicitud inválida'}), 400

        pagos = (
            PagoCompra.query.options(
                joinedload(PagoCompra.metodo),
                joinedload(PagoCompra.usuario),
            )
            .filter(PagoCompra.id_sesion_caja == id_sesion, PagoCompra.id_metodo_pago == metodo_id)
            .order_by(PagoCompra.fecha_pago.asc(), PagoCompra.id_pago_compra.asc())
            .all()
        )
        for pago in pagos:
            forma_pago = pago.metodo.nombre if pago.metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
            items.append(
                {
                    'fecha': local_strftime(pago.fecha_pago, '%d/%m/%Y %H:%M'),
                    'concepto': 'Pago de Compra',
                    'referencia': f'Compra #{pago.id_compra}',
                    'detalle': _descripcion_compra_detalle(getattr(pago, 'compra', None)),
                    'forma_pago': forma_pago,
                    'entrada': 0.0,
                    'salida': _money(pago.monto),
                    'tx_tipo': 'pago_compra',
                    'tx_id': int(pago.id_pago_compra),
                }
            )

    elif key in {'ingresos_varios', 'vuelto', 'reembolsos', 'egresos_varios'}:
        movimientos = (
            MovimientoCaja.query.options(joinedload(MovimientoCaja.usuario))
            .filter(MovimientoCaja.id_sesion_caja == id_sesion)
            .order_by(MovimientoCaja.fecha_movimiento.asc(), MovimientoCaja.id_movimiento_caja.asc())
            .all()
        )
        _enriquecer_motivos_movimientos(movimientos)
        for mov in movimientos:
            referencia_tipo = (mov.referencia_tipo or '').strip().lower()
            motivo = (mov.motivo or '').strip()
            motivo_lower = motivo.lower()

            if key == 'ingresos_varios':
                if mov.tipo != 'ingreso':
                    continue
                if referencia_tipo == 'venta':
                    continue
            elif key == 'vuelto':
                if mov.tipo != 'egreso':
                    continue
                if referencia_tipo != 'venta':
                    continue
                if not motivo_lower.startswith('vuelto'):
                    continue
            elif key == 'reembolsos':
                if mov.tipo != 'egreso':
                    continue
                if referencia_tipo != 'devolucion':
                    continue
            elif key == 'egresos_varios':
                if mov.tipo != 'egreso':
                    continue
                if referencia_tipo == 'compra':
                    continue
                if referencia_tipo == 'devolucion':
                    continue
                if referencia_tipo == 'venta' and motivo_lower.startswith('vuelto'):
                    continue
                if referencia_tipo == 'vuelto':
                    # Tolerante: el nuevo formato usa referencia_tipo='vuelto' directamente.
                    continue

            items.append(
                {
                    'fecha': local_strftime(mov.fecha_movimiento, '%d/%m/%Y %H:%M'),
                    'concepto': 'Movimiento de Caja',
                    'referencia': getattr(mov, 'motivo_detallado', None) or mov.motivo,
                    'detalle': '',
                    'forma_pago': 'Efectivo',
                    'entrada': _money(mov.monto) if mov.tipo == 'ingreso' else 0.0,
                    'salida': _money(mov.monto) if mov.tipo == 'egreso' else 0.0,
                    'tx_tipo': 'movimiento_caja',
                    'tx_id': int(mov.id_movimiento_caja),
                }
            )

    elif key == 'anulaciones_ventas_metodo':
        if not metodo_id:
            return jsonify({'error': 'Solicitud inválida'}), 400
        metodos = (
            MetodoPago.query.filter_by(activo=True)
            .order_by(MetodoPago.orden_display.asc(), MetodoPago.nombre.asc())
            .all()
        )
        metodos_por_id = {int(m.id_metodo_pago): m for m in metodos}
        efectivo_id = _resolver_metodo_efectivo_id(metodos, metodos_por_id)
        anulaciones_ctx = obtener_resumen_anulaciones_ventas_sesion(sesion, efectivo_id=efectivo_id)
        usar_movimientos_efectivo = (
            efectivo_id is not None
            and int(metodo_id) == int(efectivo_id)
            and float(anulaciones_ctx['efectivo_movimientos'] or 0.0) >= float(anulaciones_ctx['efectivo_esperado'] or 0.0)
            and bool(anulaciones_ctx['movimientos_efectivo_rows'])
        )

        rows = []
        if usar_movimientos_efectivo:
            metodo = metodos_por_id.get(int(efectivo_id))
            forma_pago = metodo.nombre if metodo else 'Efectivo'
            for row in anulaciones_ctx['movimientos_efectivo_rows']:
                venta = anulaciones_ctx['ventas_por_id'].get(int(row['id_venta']))
                if not venta:
                    continue
                fecha_anulacion = anulaciones_ctx['fecha_por_venta'].get(int(venta.id_venta)) or row['fecha'] or venta.fecha_venta
                items.append(
                    {
                        'fecha': local_strftime(fecha_anulacion, '%d/%m/%Y %H:%M'),
                        'concepto': 'Anulación de Venta',
                        'referencia': f'Venta #{venta.id_venta}',
                        'detalle': _descripcion_venta_detalle(venta),
                        'forma_pago': forma_pago,
                        'entrada': 0.0,
                        'salida': _money(row['total']),
                        'tx_tipo': 'venta',
                        'tx_id': int(venta.id_venta),
                    }
                )
        else:
            for row in anulaciones_ctx['pagos_rows']:
                if int(row.id_metodo_pago or 0) != int(metodo_id):
                    continue
                venta = anulaciones_ctx['ventas_por_id'].get(int(row.id_venta))
                if not venta:
                    continue
                fecha_anulacion = anulaciones_ctx['fecha_por_venta'].get(int(venta.id_venta)) or venta.fecha_venta
                metodo = metodos_por_id.get(int(metodo_id))
                rows.append((fecha_anulacion, venta, row, metodo))
        for fecha_accion, venta, pago, metodo in rows:
            forma_pago = metodo.nombre if metodo else f'Método #{int(getattr(pago, "id_metodo_pago", 0) or 0)}'
            monto_anulado = _money(getattr(pago, 'monto', None) or getattr(pago, 'total', 0))
            items.append(
                {
                    'fecha': local_strftime(fecha_accion, '%d/%m/%Y %H:%M'),
                    'concepto': 'Anulación de Venta',
                    'referencia': f'Venta #{venta.id_venta}',
                    'detalle': _descripcion_venta_detalle(venta),
                    'forma_pago': forma_pago,
                    'entrada': 0.0,
                    'salida': monto_anulado,
                    'tx_tipo': 'venta',
                    'tx_id': int(venta.id_venta),
                }
            )

    else:
        return jsonify({'error': 'Concepto no soportado'}), 400

    entrada_total = sum(_money(i.get('entrada')) for i in items)
    salida_total = sum(_money(i.get('salida')) for i in items)

    return jsonify(
        {
            'key': key,
            'metodo_id': metodo_id,
            'entrada_total': entrada_total,
            'salida_total': salida_total,
            'items': items,
        }
    )


@caja_bp.route('/cierres')
@login_required
def cierres_listar():
    if not current_user.tiene_permiso('ver_caja'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver la caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    raw_desde = request.args.get('desde')
    raw_hasta = request.args.get('hasta')
    cierre_abierto = request.args.get('cierre_abierto', type=int)

    if raw_desde or raw_hasta:
        desde = parse_iso_date(raw_desde) or parse_iso_date(raw_hasta) or today_local()
        hasta = parse_iso_date(raw_hasta) or parse_iso_date(raw_desde) or desde
    else:
        hasta = today_local()
        desde = today_local().replace(day=1) if hasattr(today_local(), 'replace') else hasta

    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde

    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)

    query = (
        SesionCaja.query.options(
            joinedload(SesionCaja.caja),
            joinedload(SesionCaja.usuario),
            joinedload(SesionCaja.usuario_cierre),
        )
        .filter(
            SesionCaja.estado == 'cerrada',
            SesionCaja.fecha_cierre.isnot(None),
            SesionCaja.fecha_cierre >= start_utc,
            SesionCaja.fecha_cierre < end_utc,
        )
    )

    puede_ver_otras = current_user.es_admin() or current_user.tiene_permiso('ver_otras_cajas')
    if not puede_ver_otras:
        query = query.filter(
            or_(
                SesionCaja.id_usuario == current_user.id_usuario,
                SesionCaja.id_usuario_cierre == current_user.id_usuario,
            )
        )

    cierres = query.order_by(SesionCaja.fecha_cierre.desc(), SesionCaja.id_sesion.desc()).limit(200).all()

    return render_template(
        'caja/cierres_list.html',
        cierres=cierres,
        desde=desde,
        hasta=hasta,
        puede_ver_otras=puede_ver_otras,
        cierre_abierto=cierre_abierto,
    )


@caja_bp.route('/cierres/<int:id_sesion>')
@login_required
def cierre_detalle(id_sesion):
    if not current_user.tiene_permiso('ver_caja'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver la caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    try:
        req_id = getattr(g, 'request_id', None)
        prefix = f'[{req_id}] ' if req_id else ''
        embed = request.args.get('embed')
        current_app.logger.info(
            f"{prefix}Cierre detalle: request sesion_id={id_sesion} embed={embed} user_id={current_user.id_usuario}"
        )
    except Exception:
        pass

    sesion = (
        SesionCaja.query.options(
            joinedload(SesionCaja.caja),
            joinedload(SesionCaja.usuario),
            joinedload(SesionCaja.usuario_cierre),
        )
        .get_or_404(id_sesion)
    )
    if sesion.estado != 'cerrada':
        flash('La sesión aún no está cerrada.', 'warning')
        return redirect(url_for('caja.estado'))
    if not _puede_ver_sesion(sesion):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver este cierre de caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    informe = _calcular_informe_cierre_sesion(sesion)
    try:
        req_id = getattr(g, 'request_id', None)
        prefix = f'[{req_id}] ' if req_id else ''
        current_app.logger.info(
            f"{prefix}Cierre detalle: render sesion_id={id_sesion} estado={sesion.estado}"
        )
    except Exception:
        pass
    return render_template('caja/cierre_detalle.html', **informe)


@caja_bp.route('/cierres/<int:id_sesion>/imprimir')
@login_required
def cierre_imprimir(id_sesion):
    if not current_user.tiene_permiso('ver_caja'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver la caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    sesion = (
        SesionCaja.query.options(
            joinedload(SesionCaja.caja),
            joinedload(SesionCaja.usuario),
            joinedload(SesionCaja.usuario_cierre),
        )
        .get_or_404(id_sesion)
    )
    if sesion.estado != 'cerrada':
        flash('La sesión aún no está cerrada.', 'warning')
        return redirect(url_for('caja.estado'))
    if not _puede_ver_sesion(sesion):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver este cierre de caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    informe = _calcular_informe_cierre_sesion(sesion)
    return render_template('caja/cierre_imprimir.html', **informe)


@caja_bp.route('/cierres/<int:id_sesion>/editar', methods=['GET', 'POST'])
@login_required
def cierre_editar(id_sesion):
    """Editar un cierre de caja (requiere permiso especial)"""
    if not current_user.tiene_permiso('editar_cierre_caja'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para editar cierres de caja.', 'danger')
        return redirect(url_for('main.dashboard'))

    sesion = (
        SesionCaja.query.options(
            joinedload(SesionCaja.caja),
            joinedload(SesionCaja.usuario),
            joinedload(SesionCaja.usuario_cierre),
        )
        .get_or_404(id_sesion)
    )
    if sesion.estado != 'cerrada':
        flash('Solo se pueden editar cierres ya realizados.', 'warning')
        return redirect(url_for('caja.estado'))

    if request.method == 'POST':
        nuevo_declarado = request.form.get('monto_declarado', type=float)
        nuevas_observaciones = request.form.get('observaciones', '').strip()
        motivo_edicion = request.form.get('motivo_edicion', '').strip()
        recalcular_sistema = bool(request.form.get('recalcular_sistema'))

        if nuevo_declarado is None:
            flash('Debe ingresar el monto declarado.', 'warning')
            return render_template('caja/cierre_editar.html', sesion=sesion)

        if not motivo_edicion:
            flash('Debe indicar el motivo de la edición.', 'warning')
            return render_template('caja/cierre_editar.html', sesion=sesion)

        datos_anteriores = {
            'monto_final_declarado': float(sesion.monto_final_declarado or 0),
            'monto_final_sistema': float(sesion.monto_final_sistema or 0),
            'diferencia': float(sesion.diferencia or 0),
            'observaciones': sesion.observaciones or '',
        }

        diferencia_anterior = sesion.diferencia
        monto_sistema_anterior = float(sesion.monto_final_sistema or 0)

        if recalcular_sistema:
            sesion.monto_final_sistema = float(sesion.calcular_total_efectivo() or 0)

        sesion.monto_final_declarado = nuevo_declarado
        sesion.diferencia = nuevo_declarado - float(sesion.monto_final_sistema or 0)

        nota_edicion = f"\n\n[EDITADO {local_strftime(datetime.utcnow(), '%d/%m/%Y %H:%M')} por {current_user.username}]: {motivo_edicion}"
        if nuevas_observaciones:
            sesion.observaciones = nuevas_observaciones + nota_edicion
        else:
            sesion.observaciones = (sesion.observaciones or '') + nota_edicion

        datos_nuevos = {
            'monto_final_declarado': float(nuevo_declarado),
            'monto_final_sistema': float(sesion.monto_final_sistema or 0),
            'diferencia': float(sesion.diferencia),
            'observaciones': sesion.observaciones,
            'motivo_edicion': motivo_edicion,
            'recalcular_sistema': bool(recalcular_sistema),
            'monto_final_sistema_anterior': float(monto_sistema_anterior),
        }

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='editar_cierre_caja',
                    modulo='caja',
                    descripcion=f'Editó cierre de caja sesión #{id_sesion}. Motivo: {motivo_edicion}',
                    referencia_tipo='sesion_caja',
                    referencia_id=id_sesion,
                    datos_anteriores=datos_anteriores,
                    datos_nuevos=datos_nuevos,
                    commit=False
                )
        except Exception:
            current_app.logger.exception('Error registrando auditoría de edición de cierre')

        try:
            db.session.commit()
            flash(f'Cierre editado correctamente. Diferencia anterior: ₲ {diferencia_anterior:,.0f}, nueva: ₲ {sesion.diferencia:,.0f}', 'success')
            return redirect(url_for('caja.cierre_detalle', id_sesion=id_sesion))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error guardando edición de cierre')
            flash('Error al guardar la edición.', 'danger')
            return render_template('caja/cierre_editar.html', sesion=sesion)

    return render_template('caja/cierre_editar.html', sesion=sesion)
