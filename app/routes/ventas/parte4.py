from .parte1 import *
from .parte3 import _procesar_venta_payload
from app.models import ClienteServicio
from app.services.clientes_fidelizacion import revertir_fidelizacion_por_anulacion_venta
from cobranzas.services.cuenta_service import anular_cuenta_por_cobrar


def _venta_existente_response(venta):
    total_pagado = sum(float(p.monto) for p in venta.pagos.all())
    total = float(venta.total or 0)
    vuelto = max(0, total_pagado - total)
    return {
        'success': True,
        'id_venta': venta.id_venta,
        'total': total,
        'pagado': total_pagado,
        'vuelto': float(vuelto),
        'mensaje': f'Venta #{venta.id_venta} ya estaba registrada'
    }

@ventas_bp.route('/procesar', methods=['POST'])
@login_required
@caja_abierta_required
def procesar():
    """Procesar una venta"""
    try:
        data = request.get_json(silent=True) or {}
        payload, status = _procesar_venta_payload(data)
        return jsonify(payload), status
    except IntegrityError:
        db.session.rollback()
        try:
            data = request.get_json(silent=True) or {}
            client_request_id = (data.get('client_request_id') or '').strip()
            if client_request_id:
                existente = Venta.query.filter_by(client_request_id=client_request_id).first()
                if existente:
                    return jsonify(_venta_existente_response(existente))
        except Exception:
            pass
        return jsonify({'error': 'Conflicto al registrar la venta'}), 409
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Error inesperado al procesar venta POS')
        return jsonify({
            'error': 'Ocurrio un error interno al procesar la venta. Intente nuevamente.'
        }), 500

@ventas_bp.route('/<int:id>')
@login_required
def detalle(id):
    """Ver detalle de una venta"""
    if not current_user.tiene_permiso('ver_detalle_venta'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver el detalle de ventas.', 'danger')
        return redirect(url_for('ventas.listar'))

    venta = Venta.query.options(
        joinedload(Venta.cliente),
        joinedload(Venta.cuenta_por_cobrar),
        joinedload(Venta.sesion_caja).joinedload(SesionCaja.usuario),
        joinedload(Venta.vendedor)
    ).filter(Venta.id_venta == id).first()
    if venta is None:
        abort(404)
    servicios_cliente_cobrados = (
        ClienteServicio.query.options(joinedload(ClienteServicio.servicio))
        .filter(ClienteServicio.id_venta == venta.id_venta)
        .order_by(ClienteServicio.id_cliente_servicio.asc())
        .all()
    )
    total_pagado_inmediato = sum(float(p.monto or 0) for p in venta.pagos.all())
    saldo_pendiente_actual = float(
        getattr(getattr(venta, 'cuenta_por_cobrar', None), 'saldo_pendiente', venta.saldo_pendiente) or 0
    )
    tipo_venta = (venta.tipo_venta or 'contado').strip().lower()
    if saldo_pendiente_actual <= 0:
        estado_cobro = 'pagada'
    elif total_pagado_inmediato > 0:
        estado_cobro = 'parcial'
    elif tipo_venta == 'credito':
        estado_cobro = 'pendiente'
    else:
        estado_cobro = 'pendiente'
    return render_template(
        'ventas/detalle.html',
        venta=venta,
        servicios_cliente_cobrados=servicios_cliente_cobrados,
        total_pagado_inmediato=total_pagado_inmediato,
        saldo_pendiente_actual=saldo_pendiente_actual,
        estado_cobro=estado_cobro,
    )

@ventas_bp.route('/<int:id>/anular', methods=['POST'])
@login_required
def anular(id):
    """Anular una venta"""
    venta = db.session.get(Venta, id)
    if venta is None:
        abort(404)

    if not current_user.es_admin() and not current_user.tiene_permiso('anular_venta'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para anular ventas.', 'danger')
        return redirect(url_for('ventas.detalle', id=id))
    
    if venta.estado == 'anulada':
        flash('Esta venta ya está anulada.', 'warning')
        return redirect(url_for('ventas.detalle', id=id))

    sesion_venta = getattr(venta, 'sesion_caja', None)
    if sesion_venta is not None and (sesion_venta.estado or '').strip().lower() == 'cerrada':
        flash(
            'No se puede anular una venta cuya sesión de caja ya está cerrada. '
            'Use una devolución o ajuste en una caja abierta para no alterar el cierre histórico.',
            'danger'
        )
        return redirect(url_for('ventas.detalle', id=id))

    id_autorizacion = request.form.get('id_autorizacion', type=int)
    ok, autorizacion = validar_autorizacion(id_autorizacion, 'anular_venta')
    if not ok:
        flash(str(autorizacion), 'danger')
        return redirect(url_for('ventas.detalle', id=id))

    cuenta_por_cobrar = getattr(venta, 'cuenta_por_cobrar', None)
    if cuenta_por_cobrar is not None:
        try:
            anular_cuenta_por_cobrar(cuenta_por_cobrar)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('ventas.detalle', id=id))

    devueltos_rows = (
        db.session.query(
            DetalleDevolucion.id_detalle_venta_original,
            func.coalesce(func.sum(DetalleDevolucion.cantidad), 0),
        )
        .join(Devolucion, DetalleDevolucion.id_devolucion == Devolucion.id_devolucion)
        .filter(
            Devolucion.id_venta == venta.id_venta,
            Devolucion.estado != 'anulada',
            Devolucion.accion_stock == 'retorno_stock',
        )
        .group_by(DetalleDevolucion.id_detalle_venta_original)
        .all()
    )
    devuelto_por_detalle = {
        int(r[0]): int(r[1] or 0) for r in devueltos_rows if r and r[0] is not None
    }

    reparacion_reabierta_id = None
    cliente_servicio_reabiertos = []
    if getattr(venta, 'id_reparacion', None):
        try:
            rid = int(venta.id_reparacion)
        except Exception:
            rid = None
        if rid:
            reparacion_obj = db.session.get(Reparacion, rid)
            if reparacion_obj:
                estado_anterior = (reparacion_obj.estado or '').strip()
                if estado_anterior.lower() == 'entregado':
                    reparacion_obj.estado = 'listo'
                    reparacion_obj.fecha_entrega = None
                    db.session.add(
                        ReparacionHistorialEstado(
                            id_reparacion=reparacion_obj.id_reparacion,
                            estado_anterior=estado_anterior or None,
                            estado_nuevo='listo',
                            nota=f'Reapertura por anulación de venta #{venta.id_venta}'
                        )
                    )
                    reparacion_reabierta_id = reparacion_obj.id_reparacion
            venta.id_reparacion = None

    cliente_servicio_objs = (
        ClienteServicio.query
        .filter_by(id_venta=venta.id_venta)
        .order_by(ClienteServicio.id_cliente_servicio.asc())
        .all()
    )
    for cliente_servicio_obj in cliente_servicio_objs:
        cliente_servicio_obj.id_venta = None
        cliente_servicio_obj.fecha_cierre = None
        if (cliente_servicio_obj.estado or '').strip().lower() == 'completado':
            cliente_servicio_obj.estado = 'solicitado'
        observaciones_servicio = (cliente_servicio_obj.observaciones or '').strip()
        reapertura_texto = f'Reabierto por anulación de venta #{venta.id_venta}'
        if reapertura_texto not in observaciones_servicio:
            cliente_servicio_obj.observaciones = f'{observaciones_servicio} | {reapertura_texto}'.strip(' |')
        cliente_servicio_reabiertos.append(int(cliente_servicio_obj.id_cliente_servicio))

    # Restaurar stock
    for detalle in venta.detalles.all():
        producto = detalle.producto
        if not producto or bool(getattr(producto, 'es_servicio', False)):
            continue
        cantidad_devuelta = int(devuelto_por_detalle.get(int(detalle.id_detalle_venta), 0) or 0)
        cantidad_a_restaurar = int(detalle.cantidad or 0) - cantidad_devuelta
        if cantidad_a_restaurar <= 0:
            continue
        stock_anterior = producto.stock_actual
        producto.stock_actual += cantidad_a_restaurar
        
        movimiento = MovimientoStock(
            id_producto=producto.id_producto,
            id_usuario=current_user.id_usuario,
            tipo_movimiento='entrada',
            cantidad=cantidad_a_restaurar,
            stock_anterior=stock_anterior,
            stock_nuevo=producto.stock_actual,
            referencia_tipo='anulacion_venta',
            referencia_id=venta.id_venta,
            motivo=f'Anulación de venta #{venta.id_venta}'
        )
        db.session.add(movimiento)

    movimientos_caja_venta = (
        MovimientoCaja.query.filter_by(
            id_sesion_caja=venta.id_sesion_caja,
            referencia_tipo='venta',
            referencia_id=venta.id_venta,
        )
        .order_by(MovimientoCaja.id_movimiento_caja.asc())
        .all()
    )
    from datetime import datetime

    if movimientos_caja_venta:
        for mov in movimientos_caja_venta:
            tipo_original = (mov.tipo or '').strip().lower()
            if tipo_original not in {'ingreso', 'egreso'}:
                continue
            tipo_reverso = 'egreso' if tipo_original == 'ingreso' else 'ingreso'
            motivo_base = (mov.motivo or '').strip()
            motivo_reverso = f'Anulación venta #{venta.id_venta}: {motivo_base}'.strip()
            if len(motivo_reverso) > 200:
                motivo_reverso = motivo_reverso[:200]
            db.session.add(
                MovimientoCaja(
                    id_sesion_caja=mov.id_sesion_caja,
                    id_usuario=current_user.id_usuario,
                    tipo=tipo_reverso,
                    monto=mov.monto,
                    motivo=motivo_reverso or f'Anulación venta #{venta.id_venta}',
                    referencia_tipo='anulacion_venta',
                    referencia_id=venta.id_venta,
                    fecha_movimiento=datetime.utcnow(),
                )
            )
    else:
        from app.services.caja_metodos import obtener_metodo_efectivo_id

        efectivo_id = obtener_metodo_efectivo_id(solo_activos=False)
        if efectivo_id is not None:
            total_efectivo_pagado = (
                db.session.query(func.sum(PagoVenta.monto))
                .filter(PagoVenta.id_venta == venta.id_venta, PagoVenta.id_metodo_pago == efectivo_id)
                .scalar()
            )
            if total_efectivo_pagado and Decimal(str(total_efectivo_pagado)) > 0:
                motivo_reverso = f'Anulación venta #{venta.id_venta}: ajuste efectivo'.strip()
                if len(motivo_reverso) > 200:
                    motivo_reverso = motivo_reverso[:200]
                db.session.add(
                    MovimientoCaja(
                        id_sesion_caja=venta.id_sesion_caja,
                        id_usuario=current_user.id_usuario,
                        tipo='egreso',
                        monto=total_efectivo_pagado,
                        motivo=motivo_reverso,
                        referencia_tipo='anulacion_venta',
                        referencia_id=venta.id_venta,
                        fecha_movimiento=datetime.utcnow(),
                    )
                )
    
    revertir_fidelizacion_por_anulacion_venta(
        venta,
        id_usuario=getattr(current_user, 'id_usuario', None),
    )
    venta.estado = 'anulada'
    db.session.commit()

    try:
        id_aut = int(getattr(autorizacion, 'id_autorizacion', 0) or 0) if autorizacion else None
        if not id_aut:
            id_aut = None
        registrar_auditoria(
            accion='anular_venta',
            modulo='ventas',
            descripcion=f'Anulación de venta #{venta.id_venta}',
            referencia_tipo='venta',
            referencia_id=venta.id_venta,
            id_autorizacion=id_aut
        )
    except Exception:
        pass
    
    if reparacion_reabierta_id and cliente_servicio_reabiertos:
        flash(
            f'Venta #{id} anulada. Stock restaurado. Reparación #{reparacion_reabierta_id} y {len(cliente_servicio_reabiertos)} servicio(s) del cliente reabiertos para cobrar nuevamente.',
            'success'
        )
    elif reparacion_reabierta_id:
        flash(
            f'Venta #{id} anulada. Stock restaurado. Reparación #{reparacion_reabierta_id} reabierta para cobrar nuevamente.',
            'success'
        )
    elif cliente_servicio_reabiertos:
        flash(
            f'Venta #{id} anulada. Stock restaurado. {len(cliente_servicio_reabiertos)} servicio(s) del cliente reabiertos para cobrar nuevamente.',
            'success'
        )
    else:
        flash(f'Venta #{id} anulada. Stock restaurado.', 'success')
    return redirect(url_for('ventas.detalle', id=id))

@ventas_bp.route('/<int:id>/devolucion', methods=['POST'])
@login_required
@caja_abierta_required
def crear_devolucion(id):
    """Registrar devolución parcial/total de una venta"""
    try:
        if not current_user.es_admin() and not current_user.tiene_permiso('anular_venta'):
            if getattr(current_user, 'modo_demo', False):
                return jsonify({'error': 'Sin permisos', 'mensaje': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
            return jsonify({'error': 'Sin permisos', 'modo_demo': False}), 403

        venta = db.session.get(Venta, id)
        if venta is None:
            abort(404)
        if venta.estado != 'completada':
            return jsonify({'error': 'La venta no está en estado válido para devolución'}), 400

        sesion = SesionCaja.query.filter_by(
            id_usuario=current_user.id_usuario,
            estado='abierta'
        ).first()
        if not sesion:
            return jsonify({'error': 'No hay caja abierta'}), 400

        data = request.get_json() or {}
        items = data.get('items', [])
        motivo = (data.get('motivo') or '').strip()
        accion_stock = (data.get('accion_stock') or 'retorno_stock').strip()
        metodo_reembolso = (data.get('metodo_reembolso') or 'efectivo').strip()
        observaciones = data.get('observaciones', '')
        id_autorizacion = data.get('id_autorizacion')
        if id_autorizacion in (None, ''):
            id_autorizacion = None
        else:
            id_autorizacion = int(id_autorizacion)

        if not items:
            return jsonify({'error': 'Debe indicar al menos un ítem para devolver'}), 400
        if not motivo:
            return jsonify({'error': 'Debe indicar el motivo de la devolución'}), 400
        if accion_stock not in ['retorno_stock', 'descarte', 'ninguna']:
            return jsonify({'error': 'accion_stock inválido'}), 400

        cantidades_por_detalle = {}
        for item in items:
            try:
                id_detalle_venta = int(item.get('id_detalle_venta'))
                cantidad = int(item.get('cantidad'))
            except Exception:
                return jsonify({'error': 'Ítem inválido'}), 400
            if cantidad <= 0:
                return jsonify({'error': f'Cantidad inválida para detalle {id_detalle_venta}'}), 400
            cantidades_por_detalle[id_detalle_venta] = cantidades_por_detalle.get(id_detalle_venta, 0) + cantidad

        if not cantidades_por_detalle:
            return jsonify({'error': 'Debe indicar al menos un ítem para devolver'}), 400

        ok, autorizacion = validar_autorizacion(id_autorizacion, 'anular_venta')
        if not ok:
            return jsonify({'error': str(autorizacion), 'codigo_permiso': 'anular_venta'}), 403

        detalles_venta_por_id = {int(d.id_detalle_venta): d for d in venta.detalles.all()}
        detalle_ids = sorted(int(x) for x in cantidades_por_detalle.keys())
        devueltos_rows = (
            db.session.query(
                DetalleDevolucion.id_detalle_venta_original,
                func.coalesce(func.sum(DetalleDevolucion.cantidad), 0),
            )
            .join(Devolucion, DetalleDevolucion.id_devolucion == Devolucion.id_devolucion)
            .filter(
                Devolucion.id_venta == venta.id_venta,
                Devolucion.estado != 'anulada',
                DetalleDevolucion.id_detalle_venta_original.in_(detalle_ids),
            )
            .group_by(DetalleDevolucion.id_detalle_venta_original)
            .all()
        )
        devueltos_por_detalle = {int(r[0]): int(r[1] or 0) for r in devueltos_rows if r and r[0] is not None}

        monto_total = Decimal('0')
        items_auditoria = []
        items_normalizados = []

        for id_detalle_venta in detalle_ids:
            cantidad = int(cantidades_por_detalle.get(id_detalle_venta) or 0)
            detalle_venta = detalles_venta_por_id.get(id_detalle_venta)
            if not detalle_venta:
                return jsonify({'error': f'Detalle de venta no encontrado: {id_detalle_venta}'}), 400

            cantidad_original = int(detalle_venta.cantidad)
            cantidad_devuelta = int(devueltos_por_detalle.get(id_detalle_venta) or 0)
            disponible = cantidad_original - cantidad_devuelta
            if disponible <= 0:
                return jsonify({'error': f'No hay cantidad disponible para devolver en detalle {id_detalle_venta}'}), 400
            if cantidad > disponible:
                return jsonify({'error': f'Cantidad inválida para detalle {id_detalle_venta}. Disponible: {disponible}'}), 400

            precio_unitario = Decimal(str(detalle_venta.precio_unitario))
            subtotal = precio_unitario * Decimal(str(cantidad))
            monto_total += subtotal
            items_normalizados.append((detalle_venta, cantidad, subtotal))

            items_auditoria.append({
                'id_detalle_venta': id_detalle_venta,
                'id_producto': detalle_venta.id_producto,
                'cantidad': cantidad,
                'precio_unitario': float(detalle_venta.precio_unitario or 0),
                'subtotal': float(subtotal or 0),
            })

        devolucion = Devolucion(
            id_venta=venta.id_venta,
            id_usuario=current_user.id_usuario,
            id_sesion_caja=sesion.id_sesion,
            motivo=motivo,
            accion_stock=accion_stock,
            monto_total=monto_total,
            metodo_reembolso=metodo_reembolso,
            observaciones=observaciones
        )
        db.session.add(devolucion)
        db.session.flush()

        for detalle_venta, cantidad, subtotal in items_normalizados:
            detalle_dev = DetalleDevolucion(
                id_devolucion=devolucion.id_devolucion,
                id_producto=detalle_venta.id_producto,
                id_detalle_venta_original=detalle_venta.id_detalle_venta,
                cantidad=cantidad,
                precio_unitario=detalle_venta.precio_unitario,
                subtotal=subtotal
            )
            db.session.add(detalle_dev)

            producto = detalle_venta.producto
            if accion_stock == 'retorno_stock' and producto and not producto.es_servicio:
                stock_anterior = int(producto.stock_actual or 0)
                producto.stock_actual = stock_anterior + cantidad

                movimiento_stock = MovimientoStock(
                    id_producto=producto.id_producto,
                    id_usuario=current_user.id_usuario,
                    tipo_movimiento='entrada',
                    cantidad=cantidad,
                    stock_anterior=stock_anterior,
                    stock_nuevo=int(producto.stock_actual),
                    referencia_tipo='devolucion',
                    referencia_id=devolucion.id_devolucion,
                    motivo=f'Devolución #{devolucion.id_devolucion} de venta #{venta.id_venta}'
                )
                db.session.add(movimiento_stock)

        if metodo_reembolso.lower() == 'efectivo' and monto_total > 0:
            movimiento_caja = MovimientoCaja(
                id_sesion_caja=sesion.id_sesion,
                id_usuario=current_user.id_usuario,
                tipo='egreso',
                monto=monto_total,
                motivo=f'Reembolso devolución #{devolucion.id_devolucion} venta #{venta.id_venta}',
                referencia_tipo='devolucion',
                referencia_id=devolucion.id_devolucion
            )
            db.session.add(movimiento_caja)

        try:
            with db.session.begin_nested():
                registrar_auditoria(
                    accion='crear_devolucion',
                    modulo='ventas',
                    descripcion=f'Devolución registrada para venta #{venta.id_venta}',
                    referencia_tipo='devolucion',
                    referencia_id=devolucion.id_devolucion,
                    datos_nuevos={
                        'id_venta': venta.id_venta,
                        'id_sesion_caja': sesion.id_sesion,
                        'motivo': motivo,
                        'accion_stock': accion_stock,
                        'metodo_reembolso': metodo_reembolso,
                        'monto_total': float(monto_total or 0),
                        'items': items_auditoria,
                    },
                    id_autorizacion=autorizacion.id_autorizacion if autorizacion else None,
                    commit=False
                )
        except Exception:
            pass

        db.session.commit()
        return jsonify({
            'success': True,
            'id_devolucion': devolucion.id_devolucion,
            'monto_total': float(monto_total)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


